"""Cliente tipado e mínimo da API JSON do ZAP, sobre `httpx` (implementa `ZapControl`).

Sem biblioteca de terceiros específica do ZAP. As formas de resposta vieram do spike do M0
(ZAP 2.17.0): `{"version": "2.17.0"}`, `{"Result": "OK"}`, `{"contextId": "1"}` e
`{"rules": [...]}`; erro da API é um objeto com `code` (`bad_action`, `bad_api_key`,
`url_not_in_context`...), às vezes com HTTP 400.

A chave da API segue no cabeçalho `X-ZAP-API-KEY`, nunca na URL, para não cair em logs de
proxy. Todo erro vira `ExternalToolError` com dica; mensagens trazem só o código curto da
API, nunca a chave nem o corpo da resposta.
"""

import json
import re
from typing import Final

import httpx

from harness_dast.domain.errors import ExternalToolError

_MAX_RESPONSE_BYTES: Final = 1024 * 1024
_CODE = re.compile(r"[a-z0-9_]{1,40}")
_TIMEOUT_SECONDS: Final = 15.0
_NO_ADDON: Final = "no_implementor"


class _AddonMissing(ExternalToolError):
    """O componente da API não existe no ZAP (add-on não instalado)."""


class ZapApiClient:
    """Fala com a API do ZAP; uma instância por execução."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        *,
        timeout_seconds: float = _TIMEOUT_SECONDS,
    ) -> None:
        """Cria o cliente.

        Args:
            base_url: URL base da API do ZAP (`HDAST_ZAP_BASE_URL`).
            api_key: Chave da API, ou `None` quando o ZAP não a exige.
            timeout_seconds: Tempo limite de cada chamada.
        """
        headers = {"X-ZAP-API-KEY": api_key} if api_key else {}
        self._client = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )

    def close(self) -> None:
        """Fecha as conexões."""
        self._client.close()

    def version(self) -> str:
        """Versão do ZAP (`core/view/version`)."""
        body = self._call("core", "view", "version")
        value = body.get("version")
        if not isinstance(value, str) or not value:
            raise _unexpected("core/view/version")
        return value

    def start_session(self, name: str) -> None:
        """Abre sessão nova (`core/action/newSession`), zerando histórico e contextos."""
        self._expect_ok(
            self._call("core", "action", "newSession", {"name": name, "overwrite": "true"})
        )

    def create_context(self, name: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> int:
        """Cria o contexto e devolve o identificador (`context/action/newContext`)."""
        created = self._call("context", "action", "newContext", {"contextName": name})
        context_id = created.get("contextId")
        if not isinstance(context_id, str) or not context_id.isdigit():
            raise _unexpected("context/action/newContext")
        for regex in include:
            self._expect_ok(
                self._call(
                    "context", "action", "includeInContext", {"contextName": name, "regex": regex}
                )
            )
        for regex in exclude:
            self._expect_ok(
                self._call(
                    "context", "action", "excludeFromContext", {"contextName": name, "regex": regex}
                )
            )
        return int(context_id)

    def remove_stale_rules(self, prefix: str) -> int:
        """Remove as regras do Replacer cuja descrição começa com `prefix`."""
        try:
            listing = self._call("replacer", "view", "rules")
        except _AddonMissing:
            # Sem o add-on do Replacer não há regra do harness a remover.
            return 0
        rules = listing.get("rules")
        if not isinstance(rules, list):
            raise _unexpected("replacer/view/rules")
        removed = 0
        for rule in rules:
            description = rule.get("description") if isinstance(rule, dict) else None
            if isinstance(description, str) and description.startswith(prefix):
                self._expect_ok(
                    self._call("replacer", "action", "removeRule", {"description": description})
                )
                removed += 1
        return removed

    def _call(
        self, component: str, kind: str, endpoint: str, params: dict[str, str] | None = None
    ) -> dict[str, object]:
        path = f"/JSON/{component}/{kind}/{endpoint}/"
        try:
            with self._client.stream("GET", path, params=params) as response:
                raw = self._read(response)
                status = response.status_code
        except httpx.TimeoutException:
            raise ExternalToolError(
                "O ZAP não respondeu dentro do tempo limite.",
                hint="Confira se o ZAP está no ar e não está sobrecarregado.",
            ) from None
        except httpx.HTTPError:
            raise ExternalToolError(
                "Não foi possível falar com a API do ZAP.",
                hint="Confira se o ZAP está no ar e se HDAST_ZAP_BASE_URL está certo.",
            ) from None
        return _parse(raw, status, f"{component}/{kind}/{endpoint}")

    @staticmethod
    def _read(response: httpx.Response) -> bytes:
        data = b""
        for chunk in response.iter_bytes():
            data += chunk
            if len(data) > _MAX_RESPONSE_BYTES:
                raise ExternalToolError(
                    "A resposta da API do ZAP é grande demais.",
                    hint="Confira se HDAST_ZAP_BASE_URL aponta para o ZAP.",
                )
        return data

    @staticmethod
    def _expect_ok(body: dict[str, object]) -> None:
        if body.get("Result") != "OK":
            raise _unexpected("uma ação (esperava Result OK)")


def _parse(raw: bytes, status: int, endpoint: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw)
    except (ValueError, RecursionError):
        raise _unexpected(endpoint) from None
    if not isinstance(parsed, dict):
        raise _unexpected(endpoint)
    code = parsed.get("code")
    if isinstance(code, str):
        shown = code if _CODE.fullmatch(code) else "desconhecido"
        error_type = _AddonMissing if shown == _NO_ADDON else ExternalToolError
        raise error_type(
            f"A API do ZAP recusou {endpoint} (código {shown}).", hint=_hint_for(shown)
        )
    if status != 200:
        raise _unexpected(endpoint)
    return parsed


def _hint_for(code: str) -> str:
    if code in {"bad_api_key", "no_api_key"}:
        return "Confira HDAST_ZAP_API_KEY: a chave não foi aceita pelo ZAP."
    if code == _NO_ADDON:
        return "Instale o add-on correspondente no ZAP."
    return "Confira a versão do ZAP (testado com 2.17.x) e os add-ons instalados."


def _unexpected(endpoint: str) -> ExternalToolError:
    return ExternalToolError(
        f"Resposta inesperada da API do ZAP em {endpoint}.",
        hint="Confira se HDAST_ZAP_BASE_URL aponta para o ZAP e se a versão é a 2.17.x.",
    )
