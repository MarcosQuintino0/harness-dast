"""Cliente da API de varredura do ZAP (implementa `ScanControl`), sobre `ZapApiClient`.

Reaproveita a conexão, a chave no cabeçalho e o tratamento de erro do cliente base e acrescenta
os endpoints de varredura ativa, Replacer, alertas e mensagens. As formas de resposta vêm do
spike do M0 (ZAP 2.17.0) e da documentação da API; os nomes de parâmetro marcados abaixo ainda
precisam ser conferidos contra o ZAP real (a lista está no ADR 0022):

- `ascan/action/setOption*` recebe o valor no parâmetro `Integer`;
- `ascan/action/addScanPolicy`, `disableScanners`, `removeScanPolicy` e `ascan/view/scanners`;
- `ascan/view/scans` com `progress` e `state` como texto;
- `core/view/messages` paginado por `start` e `count`.

`ascan/view/scanProgress` (métricas por regra, ADR 0031) já foi conferido contra o ZAP 2.17.0
real; a forma está em `scan_progress.py`.

O valor do token vai na consulta de `replacer/action/addRule` (a API do ZAP é chamada por GET,
como no spike), na rede de laço local. Nada disto é registrado em log.
"""

import json
from datetime import UTC, datetime
from typing import Final
from urllib.parse import urlsplit

import structlog

from harness_dast.adapters.zap.api_client import ZapApiClient
from harness_dast.adapters.zap.scan_progress import parse_scan_progress
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.oast_ssrf import OastEvent
from harness_dast.domain.rule_stats import RuleStat
from harness_dast.domain.scan_policy import (
    OAST_CALLBACK_HOST,
    OAST_CALLBACK_PORT,
    ScanLimits,
    ScanPolicy,
)
from harness_dast.domain.scan_result import OastUnavailable, ScanRefused, ScanStatus
from harness_dast.domain.scan_tokens import ReplacerRule
from harness_dast.domain.zap_messages import ZapMessage

from harness_dast.application.scan_ports import ScanStart  # isort: skip

_log = structlog.get_logger()
_OAST_MESSAGE_TYPE: Final = "22"
_OAST_PAGE: Final = 100
_AGENT_CAP: Final = 80
_MESSAGE_PAGE: Final = 10
_ALERT_PAGE: Final = 50
_MAX_PAGES: Final = 1000
_REFUSAL_CODES: Final = ("url_not_in_context", "does_not_exist", "illegal_parameter")


def _unexpected(endpoint: str) -> ExternalToolError:
    return ExternalToolError(
        f"Resposta inesperada da API do ZAP em {endpoint}.",
        hint="Confira se HDAST_ZAP_BASE_URL aponta para o ZAP e se a versão é a 2.17.x.",
    )


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _int(value: object, default: int = 0) -> int:
    return int(value) if isinstance(value, str) and value.strip().lstrip("-").isdigit() else default


def _dict_list(body: dict[str, object], key: str, endpoint: str) -> list[dict[str, object]]:
    items = body.get(key)
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise _unexpected(endpoint)
    return [item for item in items if isinstance(item, dict)]


def _oast_event(raw: dict[str, object]) -> OastEvent | None:
    """Evento do Callback (mensagem do tipo 22); outras mensagens do histórico dão `None`."""
    if _text(raw.get("type")) != _OAST_MESSAGE_TYPE:
        return None
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not identifier.isdigit():
        raise _unexpected("core/view/messages")
    lines = _text(raw.get("requestHeader", "")).splitlines()
    request_line = lines[0].split(" ") if lines else []
    if len(request_line) < 2:
        raise _unexpected("core/view/messages")
    agent = next(
        (
            line.split(":", 1)[1].strip()
            for line in lines[1:]
            if line.lower().startswith("user-agent:")
        ),
        None,
    )
    stamp = raw.get("timestamp")
    moment = (
        datetime.fromtimestamp(int(stamp) / 1000, tz=UTC).isoformat()
        if isinstance(stamp, str) and stamp.isdigit()
        else None
    )
    return OastEvent(
        event_id=int(identifier),
        path=urlsplit(request_line[1]).path,
        at=moment,
        method=request_line[0][:10],
        user_agent=_clean(agent) if agent else None,
    )


def _clean(value: str) -> str:
    return "".join(char for char in value if char.isprintable())[:_AGENT_CAP]


def _message(raw: dict[str, object], endpoint: str) -> ZapMessage:
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not identifier.isdigit():
        raise _unexpected(endpoint)
    kind = raw.get("type")
    return ZapMessage(
        id=int(identifier),
        type=kind if isinstance(kind, str) else None,
        request_header=_text(raw.get("requestHeader", "")),
        request_body=_text(raw.get("requestBody", "")),
        response_header=_text(raw.get("responseHeader", "")),
        response_body=_text(raw.get("responseBody", "")),
    )


class ZapScanClient(ZapApiClient):
    """Fala com a API de varredura do ZAP; uma instância por execução."""

    def verify_context(self, name: str, context_id: int) -> None:
        """Confere que o contexto existe com o id esperado (`context/view/context`)."""
        body = self._call("context", "view", "context", {"contextName": name})
        found = body.get("context")
        if not isinstance(found, dict) or _int(found.get("id"), -1) != context_id:
            raise ExternalToolError(
                "O contexto desta execução não existe no ZAP com o id registrado.",
                hint="O ZAP foi reiniciado ou trocou de sessão; refaça o probe.",
            )

    def list_messages(self, base_url: str) -> tuple[ZapMessage, ...]:
        """Mensagens do histórico sob `base_url`, em páginas de `_MESSAGE_PAGE`."""
        found: list[ZapMessage] = []
        for page in range(_MAX_PAGES):
            body = self._call(
                "core",
                "view",
                "messages",
                {
                    "baseurl": base_url,
                    "start": str(page * _MESSAGE_PAGE),
                    "count": str(_MESSAGE_PAGE),
                },
            )
            items = _dict_list(body, "messages", "core/view/messages")
            found.extend(_message(item, "core/view/messages") for item in items)
            if len(items) < _MESSAGE_PAGE:
                break
        return tuple(found)

    def oast_baseline(self) -> int:
        """Quantas mensagens o histórico tem agora (`core/view/numberOfMessages`)."""
        body = self._call("core", "view", "numberOfMessages")
        count = body.get("numberOfMessages")
        if not isinstance(count, str) or not count.isdigit():
            raise _unexpected("core/view/numberOfMessages")
        return int(count)

    def oast_events(self, since: int) -> tuple[OastEvent, ...]:
        """Acessos que o Callback do OAST recebeu depois de `since` (mensagens do tipo 22)."""
        found: list[OastEvent] = []
        for page in range(_MAX_PAGES):
            start = since + page * _OAST_PAGE
            body = self._call(
                "core", "view", "messages", {"start": str(start), "count": str(_OAST_PAGE)}
            )
            items = _dict_list(body, "messages", "core/view/messages")
            for item in items:
                event = _oast_event(item)
                if event is not None:
                    found.append(event)
            if len(items) < _OAST_PAGE:
                break
        return tuple(found)

    def get_message(self, message_id: int) -> ZapMessage:
        """Uma mensagem do histórico (`core/view/message`)."""
        body = self._call("core", "view", "message", {"id": str(message_id)})
        raw = body.get("message")
        if not isinstance(raw, dict):
            raise _unexpected("core/view/message")
        return _message(raw, "core/view/message")

    def apply_policy(self, policy: ScanPolicy, limits: ScanLimits) -> None:
        """Fixa limites e injeção em caminho e recria a política com as regras desligadas."""
        for option, value in (
            ("setOptionThreadPerHost", limits.threads_per_host),
            ("setOptionDelayInMs", limits.delay_ms),
            ("setOptionMaxScanDurationInMins", limits.max_scan_minutes),
            ("setOptionMaxRuleDurationInMins", limits.max_rule_minutes),
            ("setOptionTargetParamsInjectable", policy.injectable_mask),
            ("setOptionHostPerScan", 1),
        ):
            self._action("ascan", option, {"Integer": str(value)})
        # Sem isto o ZAP varre cabeçalhos de poucos pedidos; explícito nos dois sentidos (ADR 0097).
        self._action(
            "ascan",
            "setOptionScanHeadersAllRequests",
            {"Boolean": "true" if policy.header_injection else "false"},
        )
        self.remove_scan_policy(policy.name)
        self._action(
            "ascan",
            "addScanPolicy",
            {
                "scanPolicyName": policy.name,
                "attackStrength": policy.strength,
                "alertThreshold": policy.threshold,
            },
        )
        if policy.disabled_rules:
            self._require_known_rules(policy)
            ids = ",".join(str(item) for item in policy.disabled_rules)
            self._action("ascan", "disableScanners", {"ids": ids, "scanPolicyName": policy.name})
        self._verify_disabled(policy)
        if policy.oast:
            self._configure_oast(policy)
        if policy.experimental_rules:
            self._enable_experimental(policy)

    def start_scan(self, request: ScanStart) -> str:
        """Inicia a varredura de uma requisição, SEMPRE com `contextId` e sem recursão."""
        self._action(
            "ascan",
            "setOptionMaxScanDurationInMins",
            {"Integer": str(request.max_scan_minutes)},
        )
        params = {
            "url": request.url,
            "method": request.method,
            "contextId": str(request.context_id),
            "scanPolicyName": request.policy_name,
            "recurse": "false",
        }
        if request.body is not None:
            params["postData"] = request.body
        try:
            body = self._call("ascan", "action", "scan", params)
        except ExternalToolError as error:
            if any(code in error.message for code in _REFUSAL_CODES):
                raise ScanRefused(
                    f"O ZAP recusou iniciar a varredura ({error.message}).", hint=error.hint
                ) from None
            raise
        scan_id = body.get("scan")
        if not isinstance(scan_id, str) or not scan_id.isdigit():
            raise _unexpected("ascan/action/scan")
        return scan_id

    def scan_status(self, scan_id: str) -> ScanStatus:
        """Estado de uma varredura (`ascan/view/scans`)."""
        scans = _dict_list(self._call("ascan", "view", "scans"), "scans", "ascan/view/scans")
        for item in scans:
            if item.get("id") == scan_id:
                return ScanStatus(
                    scan_id=scan_id,
                    state=_text(item.get("state", "")).upper(),
                    progress=min(100, max(0, _int(item.get("progress")))),
                    requests=_int(item.get("reqCount")),
                    alerts=_int(item.get("alertCount")),
                )
        raise ExternalToolError(
            "O ZAP não conhece a varredura iniciada.", hint="Confira se o ZAP foi reiniciado."
        )

    def scan_rules(self, scan_id: str) -> tuple[RuleStat, ...]:
        """Tempo, pedidos e alertas de cada regra de uma varredura (`ascan/view/scanProgress`)."""
        body = self._call("ascan", "view", "scanProgress", {"scanId": scan_id})
        return parse_scan_progress(body)

    def stop_scan(self, scan_id: str) -> None:
        """Para uma varredura (`ascan/action/stop`)."""
        self._action("ascan", "stop", {"scanId": scan_id})

    def list_alerts(self, base_url: str) -> tuple[dict[str, str], ...]:
        """Alertas da sessão sob `base_url`, em páginas de `_ALERT_PAGE`."""
        found: list[dict[str, str]] = []
        for page in range(_MAX_PAGES):
            body = self._call(
                "alert",
                "view",
                "alerts",
                {"baseurl": base_url, "start": str(page * _ALERT_PAGE), "count": str(_ALERT_PAGE)},
            )
            items = _dict_list(body, "alerts", "alert/view/alerts")
            found.extend({str(key): _text(value) for key, value in item.items()} for item in items)
            if len(items) < _ALERT_PAGE:
                break
        return tuple(found)

    def add_replacer_rule(self, rule: ReplacerRule) -> None:
        """Instala uma regra do Replacer (`replacer/action/addRule`)."""
        self._action(
            "replacer",
            "addRule",
            {
                "description": rule.description,
                "enabled": "true",
                "matchType": rule.match_type,
                "matchRegex": "true" if rule.regex else "false",
                "matchString": rule.match_string,
                "replacement": rule.replacement,
                "initiators": "",
                "url": rule.url,
            },
        )

    def remove_replacer_rule(self, description: str) -> None:
        """Remove uma regra do Replacer pelo nome."""
        self._action("replacer", "removeRule", {"description": description})

    def remove_scan_policy(self, name: str) -> None:
        """Remove a política se ela existir; não é erro se não existe."""
        body = self._call("ascan", "view", "scanPolicyNames")
        names = body.get("scanPolicyNames")
        if not isinstance(names, list):
            raise _unexpected("ascan/view/scanPolicyNames")
        if name in names:
            self._action("ascan", "removeScanPolicy", {"scanPolicyName": name})

    def _action(self, component: str, endpoint: str, params: dict[str, str]) -> None:
        self._expect_ok(self._call(component, "action", endpoint, params))

    def _require_known_rules(self, policy: ScanPolicy) -> None:
        # O ZAP recusa `disableScanners` inteiro (does_not_exist) se UM id não existe na imagem.
        body = self._call("ascan", "view", "scanners", {"scanPolicyName": policy.name})
        known = {
            _text(item.get("id")) for item in _dict_list(body, "scanners", "ascan/view/scanners")
        }
        unknown = sorted(str(item) for item in policy.disabled_rules if str(item) not in known)
        if unknown:
            raise ExternalToolError(
                "O ZAP não tem as regras de varredura ativa " + ", ".join(unknown) + ".",
                hint="Confira a versão do ZAP (2.17.x) e os ids em scan.disable_rules do perfil.",
            )

    def _configure_oast(self, policy: ScanPolicy) -> None:
        """Aponta o Callback do OAST para a ponte do laboratório e liga as regras (ADR 0099).

        Só roda com `scan.oast`. O Callback escuta em 0.0.0.0 dentro da rede interna do ZAP e
        anuncia o nome da ponte; o ZAP não ganha rede nova nem rota externa.
        """
        try:
            self._action(
                "oast",
                "setCallbackOptions",
                {
                    "localAddress": "0.0.0.0",  # noqa: S104 - rede interna sem porta publicada
                    "remoteAddress": OAST_CALLBACK_HOST,
                    "port": str(OAST_CALLBACK_PORT),
                },
            )
            self._action("oast", "setActiveScanService", {"name": "Callback"})
        except ExternalToolError as error:
            raise OastUnavailable(
                "Não foi possível configurar o Callback OAST do ZAP.", hint=error.hint
            ) from error
        body = self._call("ascan", "view", "scanners", {"scanPolicyName": policy.name})
        known = {
            _text(item.get("id")) for item in _dict_list(body, "scanners", "ascan/view/scanners")
        }
        present = [item for item in policy.oast_rules if str(item) in known]
        absent = [item for item in policy.oast_rules if str(item) not in known]
        if absent:
            _log.warning("oast_rules_absent", ids=absent)
        if not present:
            return
        ids = ",".join(str(item) for item in present)
        self._action("ascan", "enableScanners", {"ids": ids, "scanPolicyName": policy.name})
        body = self._call("ascan", "view", "scanners", {"scanPolicyName": policy.name})
        on = {
            _text(item.get("id"))
            for item in _dict_list(body, "scanners", "ascan/view/scanners")
            if _text(item.get("enabled")).lower() == "true"
        }
        off = sorted(str(item) for item in present if str(item) not in on)
        if off:
            raise ExternalToolError(
                "Regras de retorno fora de banda continuam desligadas: " + ", ".join(off) + ".",
                hint="Confira a versão do ZAP (2.17.x) e o complemento OAST da imagem.",
            )

    def _enable_experimental(self, policy: ScanPolicy) -> None:
        """Liga as regras alpha/beta selecionadas e confere que ligaram (ADR 0103).

        Só roda com `extra_checks.experimental_rules`. Falta de regra é erro: a chave liga uma
        capacidade que a imagem estável do ZAP não tem, e seguir sem ela daria a falsa ideia de
        que a regra rodou.
        """
        body = self._call("ascan", "view", "scanners", {"scanPolicyName": policy.name})
        known = {
            _text(item.get("id")) for item in _dict_list(body, "scanners", "ascan/view/scanners")
        }
        absent = sorted(str(item) for item in policy.experimental_rules if str(item) not in known)
        if absent:
            raise ExternalToolError(
                "O ZAP não tem as regras experimentais " + ", ".join(absent) + ".",
                hint="Suba a pilha com a imagem do harness (docker/zap), que traz ascanrulesBeta "
                "e ascanrulesAlpha fixos; a imagem estável oficial não os tem.",
            )
        ids = ",".join(str(item) for item in policy.experimental_rules)
        self._action("ascan", "enableScanners", {"ids": ids, "scanPolicyName": policy.name})
        body = self._call("ascan", "view", "scanners", {"scanPolicyName": policy.name})
        on = {
            _text(item.get("id"))
            for item in _dict_list(body, "scanners", "ascan/view/scanners")
            if _text(item.get("enabled")).lower() == "true"
        }
        off = sorted(str(item) for item in policy.experimental_rules if str(item) not in on)
        if off:
            raise ExternalToolError(
                "Regras experimentais continuam desligadas: " + ", ".join(off) + ".",
                hint="Confira a versão do ZAP (2.17.x) e os complementos da imagem do harness.",
            )

    def _verify_disabled(self, policy: ScanPolicy) -> None:
        body = self._call("ascan", "view", "scanners", {"scanPolicyName": policy.name})
        scanners = _dict_list(body, "scanners", "ascan/view/scanners")
        wanted = {str(item) for item in policy.disabled_rules}
        still_on = sorted(
            _text(item.get("id"))
            for item in scanners
            if _text(item.get("id")) in wanted and _text(item.get("enabled")).lower() == "true"
        )
        if still_on:
            raise ExternalToolError(
                "Regras que deviam estar desligadas continuam ligadas: "
                + ", ".join(still_on)
                + ".",
                hint="Confira a versão do ZAP (2.17.x) e os ids em DEFAULT_DISABLED_RULES.",
            )
