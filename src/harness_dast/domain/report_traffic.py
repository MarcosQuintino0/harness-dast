"""Frases sobre a cerca de escopo para o `report.md` e o `report.html`. Módulo puro.

Texto nosso, sem marcação: cada renderizador escapa do seu jeito. Aqui ficam o modo de leitura
do caminho, o aviso de cobertura parcial de injeção em caminho (ADR 0026), a nota do modo amplo
e a lista de recusas com nome legível. Os códigos continuam visíveis ao lado do nome, para quem
quer procurar na auditoria.
"""

from harness_dast.domain.scope_labels import label_for, reading_mode_label
from harness_dast.domain.traffic import TrafficSummary, path_shape_breakdown


def mode_line(traffic: TrafficSummary) -> str:
    """Diz em que modo de leitura do caminho o proxy rodou."""
    return (
        f"Modo de leitura do caminho no proxy: {traffic.path_mode} "
        f"({reading_mode_label(traffic.path_mode)})."
    )


def denied_rows(traffic: TrafficSummary) -> tuple[tuple[str, str, int], ...]:
    """Recusas como (nome legível, código, pedidos), da maior para a menor contagem.

    Usa o código granular (`denied_by_detail`); em `scan.json` antigo, sem ele, cai no motivo
    agrupado (`denied_by_reason`).
    """
    source = traffic.denied_by_detail or traffic.denied_by_reason
    ordered = sorted(source.items(), key=lambda pair: (-pair[1], pair[0]))
    return tuple((label_for(code), code, count) for code, count in ordered)


def path_shape_warning(traffic: TrafficSummary) -> str | None:
    """Aviso de cobertura parcial de injeção em caminho, ou `None` se nada foi recusado assim."""
    if not traffic.path_shape_denied:
        return None
    total = traffic.allowed + traffic.denied
    share = traffic.path_shape_denied / total * 100 if total else 0.0
    causes = "; ".join(
        f"{label_for(code)} [{code}: {count}]"
        for code, count in sorted(path_shape_breakdown(traffic).items())
    )
    advice = (
        " O perfil usa scope.path_mode: strict; só o dono do produto pode autorizar wide na "
        "carta, e o agente não liga esse modo."
        if traffic.path_mode == "strict"
        else ""
    )
    return (
        "AVISO: a cobertura de injeção em segmento de caminho foi PARCIAL: "
        f"{traffic.path_shape_denied} de {total} pedido(s) ({share:.0f}%) foram recusados "
        f"pela forma do caminho ({causes}). Os ataques que dependem dessas formas não chegaram "
        f"ao alvo.{advice}"
    )


def outside_allow_note(traffic: TrafficSummary) -> str | None:
    """Nota do modo amplo: pedidos liberados com leitura fora de `scope.allow`, ou `None`."""
    if not traffic.allowed_outside_allow:
        return None
    return (
        f"Atenção (modo amplo): {traffic.allowed_outside_allow} pedido(s) liberados têm uma "
        "leitura do caminho fora de scope.allow (sem casar deny_paths); o servidor pode ter "
        "roteado esses pedidos para outro caminho do mesmo host (risco aceito, ADR 0026)."
    )


def backoff_warning(traffic: TrafficSummary) -> str | None:
    """Explica a lacuna de pedidos recusados durante o recuo remoto, sem atribuição inventada."""
    count = traffic.denied_by_reason.get("rate_backoff", 0)
    if count <= 0:
        return None
    return (
        f"AVISO: cobertura PARCIAL: {count} pedido(s) foram recusados durante o recuo "
        "temporário solicitado pelo destino (rate_backoff) e não chegaram ao alvo. "
        "A contagem é global da etapa; ela não comprova recuperação nem atribuição "
        "individual de cada pedido a uma regra ou operação."
    )
