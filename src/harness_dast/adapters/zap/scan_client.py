"""Cliente da API de varredura do ZAP (implementa `ScanControl`), sobre `ZapApiClient`.

Reaproveita a conexão, a chave no cabeçalho e o tratamento de erro do cliente base e acrescenta
os endpoints de varredura ativa, Replacer, alertas e mensagens. As formas de resposta vêm do
spike do M0 (ZAP 2.17.0) e da documentação da API; os nomes de parâmetro marcados abaixo ainda
precisam ser conferidos contra o ZAP real (a lista está no ADR 0022):

- `ascan/action/setOption*` recebe o valor no parâmetro `Integer`;
- `ascan/action/addScanPolicy`, `disableScanners`, `removeScanPolicy` e `ascan/view/scanners`;
- `ascan/view/scans` com `progress` e `state` como texto;
- `core/view/messages` paginado por `start` e `count`.

O valor do token vai na consulta de `replacer/action/addRule` (a API do ZAP é chamada por GET,
como no spike), na rede de laço local. Nada disto é registrado em log.
"""

import json
from typing import Final

from harness_dast.adapters.zap.api_client import ZapApiClient
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.scan_policy import ScanLimits, ScanPolicy
from harness_dast.domain.scan_result import ScanRefused, ScanStatus
from harness_dast.domain.scan_tokens import ReplacerRule
from harness_dast.domain.zap_messages import ZapMessage

from harness_dast.application.scan_ports import ScanStart  # isort: skip

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
            ids = ",".join(str(item) for item in policy.disabled_rules)
            self._action("ascan", "disableScanners", {"ids": ids, "scanPolicyName": policy.name})
        self._verify_disabled(policy)

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
