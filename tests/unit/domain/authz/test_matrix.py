"""Tabela "quem pode o quê" (ADR 0041): modelo, conferência, plano, veredito e relatório."""

from typing import Any

import pytest
from pydantic import ValidationError

from harness_dast.domain.authz.config import CHECK_ORDER, AuthzConfig
from harness_dast.domain.authz.matrix import (
    MAX_MATRIX_RULES,
    AccessRule,
    AuthzConfigError,
)
from harness_dast.domain.authz.matrix_cells import cell_from_reply, judge_matrix_cell
from harness_dast.domain.authz.matrix_plan import MatrixPlan, matrix_roles, plan_access_matrix
from harness_dast.domain.authz.matrix_report import AccessMatrixReport
from harness_dast.domain.authz.plan import plan_vertical
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.report.authz import authz_lines
from harness_dast.domain.report.authz_matrix import MAX_MARKDOWN_ROWS, matrix_html, matrix_lines
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.rig import operation

ROLES = {"rec1": "recepcao", "med1": "medico", "adm1": "admin", "pac1": "paciente"}
OPERATIONS = {
    "getConsulta": operation("getConsulta", "get", "/api/consultas/{id}"),
    "criarMedico": operation("criarMedico", "post", "/api/medicos"),
    "apagarMedico": operation("apagarMedico", "delete", "/api/medicos/{id}"),
}


def ex(
    op: str,
    method: str = "GET",
    path: str = "/api/x",
    account: str = "med1",
    status: int = 200,
) -> ExchangeRecord:
    return ExchangeRecord(
        operation_id=op,
        method=method,
        path=path,
        target=path.replace("{id}", "1"),
        account=account,
        status=status,
        content_type="application/json" if method != "GET" else None,
        body='{"nome":"x"}' if method != "GET" else None,
    )


def rule(op: str, allow: tuple[str, ...] = (), deny: tuple[str, ...] = ()) -> AccessRule:
    return AccessRule(operation=op, allow=allow, deny=deny)


def plan(
    rules: list[AccessRule], exchanges: list[ExchangeRecord], *, allow_writes: bool = False
) -> MatrixPlan:
    return plan_access_matrix(
        rules,
        exchanges,
        ROLES,
        ("paciente", "recepcao", "medico", "admin"),
        OPERATIONS,
        allow_writes=allow_writes,
    )


def cell_of(result: MatrixPlan, row: int, role: str) -> Any:
    return next(c for c in result.rows[row].cells if c.role == role)


# --- o modelo -----------------------------------------------------------------------------


def test_the_example_of_the_adr_is_accepted() -> None:
    config = AuthzConfig.model_validate(
        {
            "role_order": ["paciente", "medico", "admin"],
            "access_matrix": [
                {
                    "operation": "getConsulta",
                    "allow": ["paciente", "medico"],
                    "deny": ["recepcao"],
                },
                {"operation": "criarMedico", "allow": ["admin"], "deny": ["paciente", "medico"]},
            ],
        }
    )

    assert [r.operation for r in config.access_matrix] == ["getConsulta", "criarMedico"]


def test_an_absent_table_is_empty_and_a_check_name_exists_for_it() -> None:
    assert AuthzConfig().access_matrix == ()
    assert "access_matrix" in CHECK_ORDER


def test_an_empty_deny_is_accepted_and_the_row_is_only_documentation() -> None:
    result = plan([rule("getConsulta", allow=("medico",))], [ex("getConsulta")])

    assert result.candidates == 0
    assert [n.reason for n in result.notes] == ["nothing_to_deny"]


@pytest.mark.parametrize(
    "bad",
    [
        {"operation": "x", "allow": ["a"], "deny": ["a"]},
        {"operation": "x", "allow": ["a", "a"]},
        {"operation": "x", "deny": ["b", "b"]},
        {"operation": "x", "deny": ["com espaco"]},
        {"operation": "x", "deny": [""]},
        {"operation": "x", "deny": [f"r{n}" for n in range(21)]},
        {"operation": "x", "allow": [f"r{n}" for n in range(21)]},
        {"operation": ""},
        {"operation": "o" * 201},
        {"operation": "x", "campo_extra": 1},
        {"operation": "x", "deny": "recepcao"},
        {"operation": "x", "deny": [1]},
        {"operation": "x", "deny": {"a": 1}},
        {"operation": 7},
        {"allow": ["a"]},
        {"operation": None},
    ],
)
def test_a_malformed_rule_is_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AccessRule.model_validate(bad)


def test_the_validation_error_does_not_echo_the_value_received() -> None:
    with pytest.raises(ValidationError) as caught:
        AccessRule.model_validate({"operation": "x", "allow": ["SEGREDO-123", "SEGREDO-123"]})

    assert "SEGREDO-123" not in str(caught.value)


@pytest.mark.parametrize(
    "bad_table",
    [
        "sim",
        {"operation": "x"},
        [1],
        ["texto"],
        [{"operation": "x"}, {"operation": "x"}],
        [{"operation": f"op{n}"} for n in range(MAX_MATRIX_RULES + 1)],
    ],
)
def test_a_malformed_table_in_the_profile_is_a_config_error(bad_table: Any) -> None:
    data = valid_profile_data()
    data["authz"] = {"access_matrix": bad_table}

    with pytest.raises(ConfigError):
        ProductProfile.from_data(data)


def test_a_table_with_the_maximum_size_is_accepted() -> None:
    data = valid_profile_data()
    data["authz"] = {"access_matrix": [{"operation": f"op{n}"} for n in range(MAX_MATRIX_RULES)]}

    assert len(ProductProfile.from_data(data).authz.access_matrix) == MAX_MATRIX_RULES


def test_an_empty_table_list_is_the_same_as_no_table() -> None:
    data = valid_profile_data()
    data["authz"] = {"access_matrix": []}

    assert ProductProfile.from_data(data).authz.access_matrix == ()


# --- a conferência com o OpenAPI e as contas ---------------------------------------------


def test_a_table_that_matches_the_openapi_and_the_accounts_passes() -> None:
    config = AuthzConfig(access_matrix=(rule("getConsulta", ("medico",), ("recepcao",)),))

    config.ensure_matrix_valid(["getConsulta"], ["medico", "recepcao"])


def test_an_unknown_operation_is_an_authz_config_error_with_its_own_code() -> None:
    config = AuthzConfig(access_matrix=(rule("naoExiste", deny=("medico",)),))

    with pytest.raises(AuthzConfigError) as caught:
        config.ensure_matrix_valid(["getConsulta"], ["medico"])

    assert caught.value.code == "AUTHZ_CONFIG_INVALID"
    assert caught.value.exit_code == 2
    assert isinstance(caught.value, ConfigError)
    assert "naoExiste" in caught.value.message
    assert caught.value.hint


def test_a_role_without_an_account_is_an_authz_config_error() -> None:
    config = AuthzConfig(access_matrix=(rule("getConsulta", deny=("fantasma",)),))

    with pytest.raises(AuthzConfigError) as caught:
        config.ensure_matrix_valid(["getConsulta"], ["medico"])

    assert "fantasma" in caught.value.message


def test_an_operation_both_public_and_in_the_table_is_a_contradiction() -> None:
    config = AuthzConfig(
        public_operations=("getConsulta",), access_matrix=(rule("getConsulta", deny=("medico",)),)
    )

    with pytest.raises(AuthzConfigError):
        config.ensure_matrix_valid(["getConsulta"], ["medico"])


def test_the_error_does_not_carry_control_characters_of_a_hostile_operation_name() -> None:
    config = AuthzConfig(access_matrix=(rule("x\nFORJADO: ok", deny=("medico",)),))

    with pytest.raises(AuthzConfigError) as caught:
        config.ensure_matrix_valid(["getConsulta"], ["medico"])

    assert "\n" not in caught.value.message


# --- o plano ------------------------------------------------------------------------------


def test_one_request_per_denied_cell_prefers_the_exchange_of_an_allowed_role() -> None:
    items = [ex("getConsulta", account="rec1"), ex("getConsulta", account="med1")]
    # recepcao e paciente são proibidos; o pedido repetido é o do médico (papel permitido).
    result = plan(
        [rule("getConsulta", allow=("medico",), deny=("paciente", "admin"))],
        items,
    )

    assert [(t.role, t.actor, t.exchange.account) for t in result.sends] == [
        ("paciente", "pac1", "med1"),
        ("admin", "adm1", "med1"),
    ]
    assert result.candidates == 2
    assert result.proved == ()


def test_only_the_first_account_of_the_role_sends() -> None:
    roles = {**ROLES, "pac2": "paciente"}
    result = plan_access_matrix(
        [rule("getConsulta", allow=("medico",), deny=("paciente",))],
        [ex("getConsulta")],
        roles,
        (),
        OPERATIONS,
        allow_writes=False,
    )

    assert [t.actor for t in result.sends] == ["pac1"]


def test_an_operation_the_probe_did_not_reach_is_not_tested_with_the_reason() -> None:
    result = plan([rule("getConsulta", deny=("recepcao",))], [])

    cell = cell_of(result, 0, "recepcao")
    assert (cell.result, cell.reason) == ("not_tested", "not_reached_by_probe")
    assert result.sends == ()
    assert result.rows[0].method == "GET"
    assert result.rows[0].path == "/api/consultas/{id}"


def test_a_role_without_an_account_is_not_tested() -> None:
    roles = {"med1": "medico"}
    result = plan_access_matrix(
        [rule("getConsulta", allow=("medico",), deny=("recepcao",))],
        [ex("getConsulta")],
        roles,
        ("medico", "recepcao"),
        OPERATIONS,
        allow_writes=False,
    )

    assert cell_of(result, 0, "recepcao").reason == "no_account_for_role"
    assert result.sends == ()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
def test_writes_are_sent_only_with_allow_writes(method: str) -> None:
    items = [ex("criarMedico", method, "/api/medicos")]
    table = [rule("criarMedico", allow=("medico",), deny=("recepcao",))]

    blocked = plan(table, items, allow_writes=False)
    allowed = plan(table, items, allow_writes=True)

    assert cell_of(blocked, 0, "recepcao").reason == "writes_not_allowed"
    assert blocked.sends == ()
    assert [t.role for t in allowed.sends] == ["recepcao"]


@pytest.mark.parametrize("allow_writes", [False, True])
def test_delete_is_never_sent(allow_writes: bool) -> None:
    items = [ex("apagarMedico", "DELETE", "/api/medicos/{id}")]

    result = plan(
        [rule("apagarMedico", allow=("medico",), deny=("recepcao",))],
        items,
        allow_writes=allow_writes,
    )

    assert cell_of(result, 0, "recepcao").reason == "delete_never_tested"
    assert result.sends == ()


def test_a_role_that_is_not_in_the_rule_is_unspecified_and_never_tested() -> None:
    result = plan([rule("getConsulta", allow=("medico",), deny=("recepcao",))], [ex("getConsulta")])

    paciente = cell_of(result, 0, "paciente")
    assert (paciente.declared, paciente.result) == ("unspecified", "unspecified")
    assert {t.role for t in result.sends} == {"recepcao"}
    assert "paciente" not in {n.message for n in result.notes}


def test_an_allowed_role_is_proved_only_when_the_probe_saw_it() -> None:
    result = plan(
        [rule("getConsulta", allow=("medico", "admin"), deny=("recepcao",))],
        [ex("getConsulta", account="med1")],
    )

    assert cell_of(result, 0, "medico").result == "proved_allowed"
    assert cell_of(result, 0, "admin").result == "declared_allowed"


def test_a_denied_role_the_probe_already_saw_succeed_fails_without_sending() -> None:
    result = plan(
        [rule("getConsulta", allow=("medico",), deny=("recepcao",))],
        [ex("getConsulta", account="rec1", status=200)],
    )

    cell = cell_of(result, 0, "recepcao")
    assert (cell.result, cell.source, cell.account, cell.status) == ("failed", "probe", "rec1", 200)
    assert result.sends == ()
    assert [(t.role, t.actor) for t in result.proved] == [("recepcao", "rec1")]


def test_the_columns_follow_role_order_then_the_other_account_roles() -> None:
    assert matrix_roles(("paciente", "admin"), ROLES) == (
        "paciente",
        "admin",
        "recepcao",
        "medico",
    )


def test_an_unknown_operation_without_openapi_keeps_the_row_without_method_and_path() -> None:
    result = plan([rule("fora", deny=("recepcao",))], [])

    assert (result.rows[0].method, result.rows[0].path) == (None, None)


# --- o veredito ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_a_refusal_passes(status: int) -> None:
    assert judge_matrix_cell(status) == "passed"


@pytest.mark.parametrize("status", [200, 201, 204, 299])
def test_a_success_fails(status: int) -> None:
    assert judge_matrix_cell(status) == "failed"


@pytest.mark.parametrize("status", [301, 302, 400, 404, 409, 422, 500, 503, None])
def test_anything_else_is_inconclusive_never_safe(status: int | None) -> None:
    assert judge_matrix_cell(status) == "inconclusive"


def test_an_inconclusive_reply_becomes_a_not_tested_cell_with_the_status() -> None:
    result = plan([rule("getConsulta", allow=("medico",), deny=("recepcao",))], [ex("getConsulta")])

    cell = cell_from_reply(result.sends[0], 404)

    assert (cell.result, cell.reason, cell.status, cell.source) == (
        "not_tested",
        "inconclusive",
        404,
        "replay",
    )


# --- a verificação vertical pula o que a tabela cobre -------------------------------------


def test_vertical_skips_an_operation_covered_by_the_table() -> None:
    items = [ex("getConsulta", account="adm1")]
    roles = {"pac1": "paciente", "adm1": "admin"}

    def assigned(item: ExchangeRecord) -> str | None:
        return item.account

    plain = plan_vertical(
        items, roles, ("paciente", "admin"), assigned, frozenset({"GET"}), frozenset()
    )
    covered = plan_vertical(
        items,
        roles,
        ("paciente", "admin"),
        assigned,
        frozenset({"GET"}),
        frozenset(),
        frozenset({"getConsulta"}),
    )

    assert len(plain.tasks) == 1
    assert covered.tasks == ()
    assert [n.reason for n in covered.not_tested] == ["covered_by_access_matrix"]


# --- a tabela no relatório ----------------------------------------------------------------


def _result(rows: int = 1, hostile: str = "ok") -> AuthzResult:
    built = plan(
        [rule("getConsulta", allow=("medico",), deny=("recepcao", "admin"))],
        [ex("getConsulta", account="rec1")],
    )
    row = built.rows[0].model_copy(update={"operation_id": hostile})
    matrix = AccessMatrixReport(roles=built.roles, rows=tuple(row for _ in range(rows)))
    return AuthzResult(
        run_id="r",
        product="p",
        status="completed",
        started_at="a",
        finished_at="b",
        access_matrix=matrix,
    )


def test_the_markdown_has_the_subsection_with_columns_and_the_word_of_each_cell() -> None:
    text = "\n".join(authz_lines(_result()))

    assert "### Tabela quem pode o quê" in text
    header = next(line for line in text.splitlines() if line.startswith("| Operação"))
    assert header.index("paciente") < header.index("recepcao") < header.index("medico")
    assert "FALHOU" in text
    assert "probe" in text.split("Legenda")[0]
    assert "não testado" in text or "provado" in text
    assert "Legenda" in text


def test_a_hostile_operation_name_cannot_inject_markdown_or_html() -> None:
    hostile = "x|<script>alert(1)</script>\n# titulo [l](http://e.com)"
    result = _result(hostile=hostile)

    md = "\n".join(matrix_lines(result.access_matrix))
    html = matrix_html(result.access_matrix)

    assert "<script>" not in html
    assert "\n# titulo" not in md
    assert "&lt;script&gt;" in html


def test_the_markdown_cuts_at_100_rows_and_says_how_many_are_missing() -> None:
    result = _result(rows=MAX_MARKDOWN_ROWS + 7)

    text = "\n".join(matrix_lines(result.access_matrix))

    assert text.count("\n| ") <= MAX_MARKDOWN_ROWS + 2
    assert "e mais 7 operação(ões)" in text
    assert "authz.json" in text


def test_without_a_table_the_report_has_no_subsection() -> None:
    assert matrix_lines(None) == []
    assert matrix_html(None) == ""
    assert "### Tabela quem pode o quê" not in "\n".join(
        authz_lines(
            AuthzResult(
                run_id="r", product="p", status="completed", started_at="a", finished_at="b"
            )
        )
    )


def test_the_html_says_the_result_in_words_and_not_only_in_color() -> None:
    html = matrix_html(_result().access_matrix)

    assert "FALHOU" in html
    assert ">-<" in html or ">pode<" in html or "provado" in html
