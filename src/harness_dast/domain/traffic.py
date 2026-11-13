"""Resumo do tráfego que o proxy de escopo viu durante uma varredura. Módulo puro.

A fonte é a trilha de auditoria do proxy (uma linha por pedido que chegou a ele, liberado ou
negado). Serve para provar, com dado de quem está no meio do caminho, a taxa efetiva e quantos
pedidos o varredor tentou fora do escopo.
"""

from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from pydantic import ConfigDict, Field

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.scope_reason import PATH_SHAPE_CODES, WIDE_READING_OUTSIDE_ALLOW


class ProxyRow(ApiModel):
    """Uma linha da auditoria do proxy (só os campos usados aqui).

    Attributes:
        at: Instante do pedido.
        decision: `allow` ou `deny`.
        reason: Motivo registrado pelo proxy.
        method: Método HTTP.
        detail: Código granular da recusa por forma, ou a marca de leitura fora de `allow` do
            modo amplo; `None` em linhas antigas ou sem detalhe.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    at: datetime
    decision: str
    reason: str
    method: str
    detail: str | None = None


class TrafficSummary(ApiModel):
    """O que o proxy viu entre o início e o fim do scan.

    Attributes:
        enabled: Se havia auditoria do proxy para ler (pilha gerenciada).
        allowed: Pedidos liberados.
        denied: Pedidos negados (o varredor tentou fora do escopo).
        denied_by_reason: Negados por motivo (recusa por forma agrupada em `malformed_request`).
        denied_by_detail: Negados por motivo GRANULAR (`path_encoded_slash`, `url_forbidden_char`,
            `deny_path`...): o código de `detail` quando há, senão o próprio motivo.
        path_shape_denied: Quantos negados foram por forma do caminho (`;`, `%2f`, `..`, dupla
            codificação, ponto ou espaço final...). É o que impede a injeção em caminho.
        allowed_outside_allow: No modo amplo, liberados com alguma leitura do caminho fora de
            `scope.allow` (o risco aceito do ADR 0026). Zero no modo estrito.
        path_mode: Modo de leitura do caminho em que o proxy rodou (`strict` ou `wide`).
        allowed_by_method: Liberados por método.
        duration_seconds: Do primeiro ao último pedido.
        average_rps: Liberados por segundo na duração observada.
        peak_rps: Maior número de liberados em um mesmo segundo.
        limit_rps: Limite do perfil (`requests_per_second`).
    """

    enabled: bool = False
    allowed: int = 0
    denied: int = 0
    denied_by_reason: dict[str, int] = Field(default_factory=dict)
    denied_by_detail: dict[str, int] = Field(default_factory=dict)
    path_shape_denied: int = 0
    allowed_outside_allow: int = 0
    path_mode: str = "strict"
    allowed_by_method: dict[str, int] = Field(default_factory=dict)
    duration_seconds: float = 0.0
    average_rps: float = 0.0
    peak_rps: int = 0
    limit_rps: float | None = None


def path_shape_breakdown(summary: TrafficSummary) -> dict[str, int]:
    """Negados por forma do caminho, por código granular (base do aviso de cobertura parcial)."""
    return {
        code: count for code, count in summary.denied_by_detail.items() if code in PATH_SHAPE_CODES
    }


def summarize_traffic(
    rows: Sequence[ProxyRow],
    *,
    start: datetime,
    end: datetime,
    limit_rps: float,
    path_mode: str = "strict",
) -> TrafficSummary:
    """Resume as linhas do intervalo `[start, end]`; `path_mode` é o modo da política."""
    inside = [row for row in rows if start <= row.at <= end]
    allowed = [row for row in inside if row.decision == "allow"]
    denied = [row for row in inside if row.decision != "allow"]
    span = (inside[-1].at - inside[0].at).total_seconds() if len(inside) > 1 else 0.0
    per_second = Counter(int(row.at.timestamp()) for row in allowed)
    by_detail = Counter(row.detail or row.reason for row in denied)
    return TrafficSummary(
        enabled=True,
        allowed=len(allowed),
        denied=len(denied),
        denied_by_reason=dict(Counter(row.reason for row in denied)),
        denied_by_detail=dict(by_detail),
        path_shape_denied=sum(n for code, n in by_detail.items() if code in PATH_SHAPE_CODES),
        allowed_outside_allow=sum(1 for row in allowed if row.detail == WIDE_READING_OUTSIDE_ALLOW),
        path_mode=path_mode,
        allowed_by_method=dict(Counter(row.method for row in allowed)),
        duration_seconds=round(span, 3),
        average_rps=round(len(allowed) / span, 2) if span > 0 else 0.0,
        peak_rps=max(per_second.values(), default=0),
        limit_rps=limit_rps,
    )
