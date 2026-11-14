"""Subseção "Tabela quem pode o quê" do `report.md` e do `report.html` (ADR 0041). Módulo puro.

Operações nas linhas, papéis nas colunas e uma palavra curta em cada quadradinho (nunca só
cor): `pode`, `provado`, `passou`, `FALHOU`, `não testado: <motivo>` e `-`. Nome de operação,
de papel e de motivo vêm do OpenAPI e do perfil e passam por `escape_inline`, `code_span` e
`html_safe`. O Markdown mostra no máximo 100 linhas; o resto está em `authz.json`.
"""

from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.authz_matrix_report import AccessMatrixReport, CellResult, MatrixCell
from harness_dast.domain.markdown_safe import code_span, escape_inline

MAX_MARKDOWN_ROWS: Final = 100
MAX_HTML_ROWS: Final = 500

CELL_WORD: Final[dict[CellResult, str]] = {
    "declared_allowed": "pode",
    "proved_allowed": "provado",
    "passed": "passou",
    "failed": "FALHOU",
    "not_tested": "não testado",
    "unspecified": "-",
}
"""Palavra de cada resultado; `provado` é "pode" visto pelo `probe` e `-` é papel não citado."""

LEGEND: Final = (
    "`pode`: declarado permitido (a ferramenta não testa permissão); `provado`: permitido e o "
    "probe obteve 2xx com conta do papel; `passou`: proibido e o servidor negou (401 ou 403); "
    "`FALHOU`: proibido e o servidor aceitou (2xx), ou o probe já o provou; `não testado`: "
    "proibido, mas não deu para testar (o motivo vem junto); `-`: papel que a tabela não cita "
    "(nunca testado e nunca presumido proibido)."
)
HEADING: Final = "Tabela quem pode o quê"
_NOTICE: Final = (
    "A tabela é declaração do dono do produto, aprovada por uma pessoa; a ferramenta só testa "
    "as proibições. Uma tabela com omissões não prova que o resto é seguro."
)


def _status(cell: MatrixCell) -> str:
    return f" ({cell.status})" if cell.status is not None else ""


def _cell_text(cell: MatrixCell) -> str:
    word = CELL_WORD[cell.result]
    if cell.result == "not_tested":
        return f"{word}: {cell.reason or 'sem motivo'}"
    if cell.result in {"passed", "failed"}:
        origin = " (probe)" if cell.source == "probe" else ""
        return f"{word}{_status(cell)}{origin}"
    return word


def matrix_lines(matrix: AccessMatrixReport | None) -> list[str]:
    """Subseção do Markdown; vazia quando o perfil não declara a tabela."""
    if matrix is None or not matrix.rows:
        return []
    header = "| Operação | " + " | ".join(escape_inline(role, 40) for role in matrix.roles) + " |"
    lines = [
        "",
        f"### {HEADING}",
        "",
        f"> {escape_inline(_NOTICE, 400)}",
        "",
        header,
        "|---|" + "---|" * len(matrix.roles),
    ]
    for row in matrix.rows[:MAX_MARKDOWN_ROWS]:
        where = f"{row.method} {row.path}" if row.method and row.path else row.operation_id
        name = f"{code_span(row.operation_id, 80)} {code_span(where, 120)}"
        cells = " | ".join(escape_inline(_cell_text(cell), 80) for cell in row.cells)
        lines.append(f"| {name} | {cells} |")
    hidden = len(matrix.rows) - MAX_MARKDOWN_ROWS
    if hidden > 0:
        lines.append(f"\n... e mais {hidden} operação(ões); veja `access_matrix` em authz.json.")
    lines += ["", f"Legenda: {LEGEND}"]
    return lines


_CLASS: Final[dict[CellResult, str]] = {
    "declared_allowed": "muted",
    "proved_allowed": "muted",
    "passed": "badge low",
    "failed": "badge high",
    "not_tested": "badge medium",
    "unspecified": "muted",
}


def _html_cell(cell: MatrixCell) -> str:
    return f'<td><span class="{_CLASS[cell.result]}">{h.text(_cell_text(cell), 80)}</span></td>'


def matrix_html(matrix: AccessMatrixReport | None) -> str:
    """Subseção do HTML; vazia quando o perfil não declara a tabela."""
    if matrix is None or not matrix.rows:
        return ""
    head = "".join(f"<th>{h.text(role, 40)}</th>" for role in matrix.roles)
    body = []
    for row in matrix.rows[:MAX_HTML_ROWS]:
        where = f"{row.method} {row.path}" if row.method and row.path else ""
        shown = f" <code>{h.ident(where, 120)}</code>" if where else ""
        cells = "".join(_html_cell(cell) for cell in row.cells)
        body.append(f"<tr><td>{h.ident(row.operation_id, 80)}{shown}</td>{cells}</tr>")
    return (
        f"<h3>{HEADING}</h3>"
        f'<p class="note">{h.plain(_NOTICE)}</p>'
        f"<table><tr><th>Operação</th>{head}</tr>{''.join(body)}</table>"
        f'<p class="muted">Legenda: {h.plain(LEGEND.replace("`", ""))}</p>'
    )
