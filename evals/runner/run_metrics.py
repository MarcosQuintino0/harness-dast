"""Leitura tolerante do `metrics.json` de uma execucao (ADR 0031, `schema_version: 1`).

O arquivo vem de fora da avaliacao (da CLI, em outra maquina ou versao): todo campo e opcional,
campo com tipo errado vira "sem dado" e `schema_version` desconhecido ou arquivo invalido devolve
`None`. Nunca levanta erro nem inventa zero: quem consome imprime `n/d`.
"""

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict

SUPPORTED_SCHEMA_VERSION = 1
CLI_STAGES = ("preflight", "probe", "scan", "authz", "report")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _text(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    return str(value)


def _dict_or_none(value: Any) -> Any:
    return value if isinstance(value, dict) else None


def _usable_rules(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and _text(item.get("plugin_id"))]


def _seconds_by_stage(value: Any) -> dict[str, float | None]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _number(item) for key, item in value.items()}


Number = Annotated[float | None, BeforeValidator(_number)]
Text = Annotated[str | None, BeforeValidator(_text)]


class _Tolerant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class RuleTotalIn(_Tolerant):
    """Uma linha de `rules.totals[]`: a regra do ZAP somada na execucao."""

    plugin_id: Text = None
    name: Text = None
    time_ms: Number = None
    requests: Number = None
    alerts: Number = None


class RulesIn(_Tolerant):
    """O bloco `rules`."""

    totals: Annotated[list[RuleTotalIn], BeforeValidator(_usable_rules)] = []


class GapsIn(_Tolerant):
    """O bloco `traffic.gaps` (silencios do proxy acima do limite)."""

    count: Number = None
    total_seconds: Number = None
    longest_seconds: Number = None


class TrafficIn(_Tolerant):
    """O bloco `traffic`."""

    gaps: Annotated[GapsIn | None, BeforeValidator(_dict_or_none)] = None


class RunMetricsIn(_Tolerant):
    """O `metrics.json` da execucao, so com o que a avaliacao le."""

    schema_version: int | None = None
    stages_seconds: Annotated[dict[str, float | None], BeforeValidator(_seconds_by_stage)] = {}
    rules: Annotated[RulesIn | None, BeforeValidator(_dict_or_none)] = None
    traffic: Annotated[TrafficIn | None, BeforeValidator(_dict_or_none)] = None


def parse_run_metrics(data: Any) -> RunMetricsIn | None:
    """Le o conteudo ja decodificado de um `metrics.json`.

    Returns:
        O modelo, ou `None` se nao e um objeto, nao tem `schema_version` 1 ou nao cabe no modelo.
    """
    if not isinstance(data, dict) or data.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        return None
    try:
        return RunMetricsIn.model_validate(data)
    except ValueError:
        return None
