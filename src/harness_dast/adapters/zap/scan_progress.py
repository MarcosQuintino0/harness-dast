"""Tradução da resposta de `ascan/view/scanProgress` do ZAP para `RuleStat` (ADR 0031).

Forma REAL medida no ZAP 2.17.0 (Clínica Piloto, 2026-11-14): uma lista cujo primeiro item é o
nome do host (texto) e o segundo um objeto com `HostProcess`, uma lista de objetos `Plugin`, cada
um com sete textos, nesta ordem:

    ["Path Traversal", "6", "release", "Complete", "1175", "40", "0"]
     nome,             id, qualidade,  estado,     ms,     pedidos, alertas

O estado é `Complete`, `Pending`, `Running` ou `Skipped, <motivo em texto>`. O texto do motivo
NUNCA é guardado: vira um código fechado. Qualquer desvio de forma levanta `ExternalToolError`
(quem chama marca a métrica como indisponível; a varredura segue).
"""

from typing import Final

from pydantic import BaseModel, ConfigDict, ValidationError

from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.rule_stats import MAX_RULE_NAME, RuleStat, RuleState

_ENDPOINT: Final = "ascan/view/scanProgress"
_FIELDS: Final = 7
_MAX_RULES: Final = 5000
_SKIP_REASONS: Final = (("exceeded max rule time", "max_rule_time"),)


class _PluginRow(BaseModel):
    """Os sete textos de um `Plugin`; o que não é número vira `None` ou erro."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    name: str
    plugin_id: str
    quality: str
    status: str
    time_ms: str
    requests: str
    alerts: str


def _unexpected() -> ExternalToolError:
    return ExternalToolError(
        f"Resposta inesperada da API do ZAP em {_ENDPOINT}.",
        hint="Confira se a versão do ZAP é a 2.17.x; as métricas por regra ficam indisponíveis.",
    )


def _number(value: str) -> int | None:
    text = value.strip()
    return int(text) if text.isdigit() else None


def _state(status: str) -> tuple[RuleState, str | None]:
    text = status.strip().lower()
    if text == "complete":
        return "completed", None
    if text == "pending":
        return "pending", None
    if text == "running":
        return "interrupted", None
    if text.startswith("skipped"):
        reason = next((code for needle, code in _SKIP_REASONS if needle in text), "other")
        return "skipped", reason
    return "unknown", None


def _plugins(body: dict[str, object]) -> list[list[object]]:
    items = body.get("scanProgress")
    if not isinstance(items, list):
        raise _unexpected()
    found: list[list[object]] = []
    for item in items:
        if isinstance(item, str):
            continue
        processes = item.get("HostProcess") if isinstance(item, dict) else None
        if not isinstance(processes, list):
            raise _unexpected()
        for process in processes:
            plugin = process.get("Plugin") if isinstance(process, dict) else None
            if not isinstance(plugin, list):
                raise _unexpected()
            found.append(plugin)
    if len(found) > _MAX_RULES:
        raise _unexpected()
    return found


def _rule(plugin: list[object]) -> RuleStat:
    parts = [part for part in plugin if isinstance(part, str)]
    if len(plugin) != _FIELDS or len(parts) != _FIELDS:
        raise _unexpected()
    try:
        row = _PluginRow(
            name=parts[0],
            plugin_id=parts[1],
            quality=parts[2],
            status=parts[3],
            time_ms=parts[4],
            requests=parts[5],
            alerts=parts[6],
        )
    except ValidationError:
        raise _unexpected() from None
    plugin_id = _number(row.plugin_id)
    if plugin_id is None:
        raise _unexpected()
    state, reason = _state(row.status)
    return RuleStat(
        plugin_id=plugin_id,
        name=row.name[:MAX_RULE_NAME],
        state=state,
        time_ms=_number(row.time_ms),
        requests=_number(row.requests) or 0,
        alerts=_number(row.alerts) or 0,
        skip_reason=reason,
    )


def parse_scan_progress(body: dict[str, object]) -> tuple[RuleStat, ...]:
    """Converte a resposta de `ascan/view/scanProgress` em medições por regra.

    Raises:
        ExternalToolError: A resposta não tem a forma conhecida (lista de `HostProcess` com
            `Plugin` de sete textos, id numérico).
    """
    return tuple(_rule(plugin) for plugin in _plugins(body))
