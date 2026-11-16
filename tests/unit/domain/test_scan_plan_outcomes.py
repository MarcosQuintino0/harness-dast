"""Plano da varredura com classes extras (ADR 0050): a classe abre a porta, as travas ficam."""

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.probe_result import OperationResult
from harness_dast.domain.scan_config import ScanConfig
from harness_dast.domain.scan_plan import (
    Candidate,
    ScanSkip,
    last_sent,
    resolve_include_outcomes,
    select_candidates,
)
from tests.unit.domain.report_helpers import operation
from tests.unit.domain.test_scan_domain import audit_result


def _plan(
    ops: list[OperationResult],
    include: frozenset[str],
    *,
    decisions: dict[str, str] | None = None,
    login_path: str | None = None,
    depends: dict[str, tuple[str, ...]] | None = None,
) -> tuple[tuple[Candidate, ...], tuple[ScanSkip, ...]]:
    sent = {
        op.operation_id: last_sent(
            [audit_result(i, op.operation_id, op.method, op.path, op.status or 404)]
        )[op.operation_id]
        for i, op in enumerate(ops, start=1)
    }
    planned = {
        op.operation_id: PlannedOperation.model_validate(
            {
                "operation_id": op.operation_id,
                "method": op.method,
                "path": op.path,
                "decision": (decisions or {}).get(op.operation_id, "send"),
                "depends_on": (depends or {}).get(op.operation_id, ()),
            }
        )
        for op in ops
    }
    return select_candidates(
        ops, planned, sent, login_path=login_path, config=ScanConfig(), include_outcomes=include
    )


def _reasons(skipped: tuple[ScanSkip, ...]) -> dict[str, str]:
    return {item.operation_id: item.reason for item in skipped}


def test_an_included_class_makes_the_operation_a_candidate_with_its_seed() -> None:
    ops = [operation("a", "GET", "/a/1", "not_found"), operation("b", "GET", "/b", "success")]

    candidates, skipped = _plan(ops, frozenset({"not_found"}))

    assert [c.result.operation_id for c in candidates] == ["a", "b"]
    assert [c.seed_outcome for c in candidates] == ["not_found", None]
    assert skipped == ()


def test_another_class_stays_out_as_not_success() -> None:
    ops = [operation("a", "GET", "/a/1", "validation_error")]

    candidates, skipped = _plan(ops, frozenset({"not_found"}))

    assert candidates == ()
    assert _reasons(skipped) == {"a": "not_success"}


def test_without_the_list_nothing_changes() -> None:
    ops = [operation("a", "GET", "/a/1", "not_found"), operation("b", "GET", "/b", "success")]

    candidates, skipped = _plan(ops, frozenset())

    assert [c.result.operation_id for c in candidates] == ["b"]
    assert _reasons(skipped) == {"a": "not_success"}


@pytest.mark.parametrize("name", ["auth_error", "server_error", "rate_limited", "timeout"])
def test_a_class_outside_the_closed_list_is_ignored_by_the_plan(name: str) -> None:
    ops = [operation("a", "GET", "/a/1", name)]

    candidates, skipped = _plan(ops, frozenset({name}))

    assert candidates == ()
    assert _reasons(skipped) == {"a": "not_success"}


def test_protections_hold_even_with_every_class_included() -> None:
    every = frozenset(
        {"logical_failure", "validation_error", "conflict", "not_found", "client_error"}
    )
    ops = [
        operation("del", "DELETE", "/d/1", "not_found"),
        operation("login", "POST", "/login", "validation_error"),
        operation("deny", "GET", "/deny", "not_found"),
        operation("out", "GET", "/out", "not_found"),
        operation("put", "PUT", "/p/1", "conflict"),
    ]

    candidates, skipped = _plan(
        ops,
        every,
        decisions={"deny": "skipped_denied", "out": "skipped_scope"},
        login_path="/login",
    )

    assert candidates == ()
    assert _reasons(skipped) == {
        "del": "delete",
        "login": "login",
        "deny": "denied",
        "out": "scope",
        "put": "mutating",
    }


def test_a_put_over_a_resource_created_by_the_run_is_allowed_with_the_class() -> None:
    ops = [operation("criar", "POST", "/p", "success"), operation("put", "PUT", "/p/1", "conflict")]

    candidates, _ = _plan(ops, frozenset({"conflict"}), depends={"put": ("criar",)})

    assert [c.result.operation_id for c in candidates] == ["criar", "put"]
    assert candidates[1].seed_outcome == "conflict"


def test_resolve_uses_the_profile_list_without_a_flag() -> None:
    assert resolve_include_outcomes(("not_found", "conflict"), None) == ("not_found", "conflict")
    assert resolve_include_outcomes((), None) == ()


def test_resolve_narrows_inside_the_profile_in_the_profile_order() -> None:
    assert resolve_include_outcomes(("not_found", "conflict"), ("conflict",)) == ("conflict",)
    assert resolve_include_outcomes(("not_found", "conflict"), ("conflict", "not_found")) == (
        "not_found",
        "conflict",
    )
    assert resolve_include_outcomes(("not_found",), ()) == ()


@pytest.mark.parametrize("requested", [("conflict",), ("not_found", "conflict")])
def test_resolve_refuses_a_class_the_profile_does_not_list(requested: tuple[str, ...]) -> None:
    with pytest.raises(ConfigError, match="não lista") as caught:
        resolve_include_outcomes(("not_found",), requested)

    assert "conflict" in caught.value.message
    assert "carta" in (caught.value.hint or "")


@pytest.mark.parametrize("requested", [("server_error",), ("auth_error",), ("",), ("NOT_FOUND",)])
def test_resolve_refuses_a_class_outside_the_closed_list(requested: tuple[str, ...]) -> None:
    with pytest.raises(ConfigError, match="include-outcome aceita só"):
        resolve_include_outcomes(("not_found",), requested)


@pytest.mark.parametrize("login_path", ["/api/session", "/api/access"])
def test_recusa_do_login_tem_motivo_login_antes_de_nao_sucesso(login_path: str) -> None:
    ops = [
        operation("session", "POST", login_path, "auth_rejected_expected"),
        operation("other_method", "GET", login_path, "auth_error"),
        operation("protected", "POST", "/api/private", "auth_error"),
    ]

    candidates, skipped = _plan(ops, frozenset(), login_path=login_path)

    assert candidates == ()
    assert _reasons(skipped) == {
        "session": "login",
        "other_method": "not_success",
        "protected": "not_success",
    }
