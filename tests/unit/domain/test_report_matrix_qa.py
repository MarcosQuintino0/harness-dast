"""QA independente da V1.4: papel, operação e caminho hostis na tabela não viram marcação."""

import re

import pytest

from harness_dast.domain.authz.matrix_report import AccessMatrixReport, MatrixCell, MatrixRow
from harness_dast.domain.report_html import render_html
from harness_dast.domain.report_markdown import render_markdown
from tests.unit.domain.test_report_html import XSS, parse
from tests.unit.domain.test_report_html_authz import with_authz

ROLE = "<img/src=x/onerror=alert(1)>"


def _matrix(role: str, op: str, path: str, reason: str) -> AccessMatrixReport:
    cells = tuple(
        MatrixCell(
            role=role,
            declared="deny",
            result=result,
            status=403,
            account=XSS,
            reason=reason,
            message=XSS,
        )
        for result in ("passed", "failed", "not_tested")
    )
    row = MatrixRow(operation_id=op, method="GET", path=path, cells=cells[:1])
    return AccessMatrixReport(
        roles=(role,), rows=(row, row.model_copy(update={"cells": cells[1:2]}))
    )


@pytest.mark.parametrize("text_", [XSS, ROLE, "x\n</td><script>alert(1)</script>"])
def test_html_never_turns_matrix_text_into_markup_or_leaks_a_token(text_: str) -> None:
    base = with_authz()
    result = base.authz.model_copy(  # type: ignore[union-attr]
        update={"access_matrix": _matrix(text_, text_, f"/x/{text_}", text_)}
    )

    page = render_html(base.model_copy(update={"authz": result}))

    parsed = parse(page)
    assert "script" not in parsed.tags
    assert "img" not in parsed.tags
    assert not any(name.startswith("on") for name, _ in parsed.attrs)


def test_markdown_matrix_row_keeps_its_column_count_when_operation_or_path_has_a_pipe() -> None:
    base = with_authz()
    result = base.authz.model_copy(  # type: ignore[union-attr]
        update={"access_matrix": _matrix("admin", "ler|x|y", "/a|b", "writes_not_allowed")}
    )

    md = render_markdown(base.model_copy(update={"authz": result}))

    rows = [line for line in md.splitlines() if line.startswith("| `ler")]
    assert rows
    for line in rows:
        cells = re.split(r"(?<!\\)\|", line.strip())
        assert len(cells) == 4  # vazio, operação, papel, vazio
