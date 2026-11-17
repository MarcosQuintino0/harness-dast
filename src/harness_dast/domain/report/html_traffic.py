"""Seção "Tráfego recusado pela cerca de escopo" do `report.html`. Módulo puro.

Mostra o modo de leitura do caminho, o aviso de cobertura parcial de injeção em caminho, as
recusas com nome legível (o código fica ao lado) e, no modo amplo, quantos pedidos foram
liberados com leitura fora de `scope.allow`. Motivo desconhecido aparece como veio: não há
tabela fechada. Todo texto passa por `html_safe`.
"""

from harness_dast.domain import html_safe as h
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.report.traffic import (
    backoff_warning,
    denied_rows,
    mode_line,
    outside_allow_note,
    path_shape_warning,
)


def traffic_section(report: FindingsReport) -> str:
    """Seção do tráfego visto pelo proxy de escopo."""
    traffic = report.coverage.traffic
    head = "<h2>Tráfego recusado pela cerca de escopo</h2>"
    if not traffic.enabled:
        return head + "<p>Não medido: não havia auditoria do proxy de escopo nesta execução.</p>"
    rows = "".join(
        f"<tr><td>{h.text(label, 160)}</td><td><code>{h.text(code, 120)}</code></td>"
        f"<td>{count}</td></tr>"
        for label, code, count in denied_rows(traffic)
    )
    cause = (
        "por escopo, forma ambígua ou limite temporário"
        if traffic.denied_by_reason.get("rate_backoff", 0)
        else "por estarem fora do escopo da carta ou com forma de caminho ambígua"
    )
    denied = (
        f"<p><b>{traffic.denied}</b> pedido(s) do varredor foram recusados {cause}. "
        "Nenhum deles chegou ao alvo.</p>"
        f"<table><tr><th>Motivo</th><th>Código</th><th>Pedidos</th></tr>{rows}</table>"
        if traffic.denied
        else "<p>Nenhum pedido foi recusado.</p>"
    )
    notes = "".join(
        f'<div class="banner">{h.text(note, 900)}</div>'
        for note in (
            backoff_warning(traffic),
            path_shape_warning(traffic),
            outside_allow_note(traffic),
        )
        if note
    )
    limit = f"; limite do perfil {traffic.limit_rps:g} req/s" if traffic.limit_rps else ""
    return (
        f"{head}<p>{h.text(mode_line(traffic), 300)}</p>{notes}{denied}"
        f'<p class="muted">{traffic.allowed} pedido(s) liberados em '
        f"{traffic.duration_seconds:g} s (média {traffic.average_rps:g} req/s, pico "
        f"{traffic.peak_rps} em 1 s{limit}).</p>"
    )
