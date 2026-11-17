"""Plano e decisões de "pedido sem login" e "token adulterado"."""

import pytest

from harness_dast.domain.api_model import Operation, SecurityRequirement
from harness_dast.domain.authz.anonymous import (
    MAX_ANONYMOUS_OPERATIONS,
    MAX_TAMPERED_OPERATIONS,
    accepted_variants,
    anonymous_severity,
    conclude_variants,
    declared_anonymous,
    plan_access,
    tampered_cwe,
)
from harness_dast.domain.authz.plan import Planned
from harness_dast.domain.probe_exchange import ExchangeRecord

BEARER = (SecurityRequirement(schemes=("bearer",)),)


def op(op_id: str, security: tuple[SecurityRequirement, ...] = BEARER) -> Operation:
    return Operation(operation_id=op_id, method="get", path=f"/api/{op_id}", security=security)


def ex(
    op_id: str, method: str = "GET", path: str | None = None, target: str | None = None
) -> ExchangeRecord:
    return ExchangeRecord(
        operation_id=op_id,
        method=method,
        path=path or f"/api/{op_id}",
        target=target or f"/api/{op_id}",
        account="a1",
        status=200,
    )


def plan(
    exchanges: list[ExchangeRecord],
    operations: dict[str, Operation] | None = None,
    public: frozenset[str] = frozenset(),
    infra: frozenset[str] = frozenset(),
    check: str = "anonymous_access",
) -> Planned[ExchangeRecord]:
    ops = operations or {e.operation_id: op(e.operation_id) for e in exchanges}
    return plan_access(check, exchanges, ops, public, infra)  # type: ignore[arg-type]


def reasons(planned: Planned[ExchangeRecord]) -> dict[str, str]:
    return {n.operation_id or "-": n.reason for n in planned.not_tested}


# --- declared_anonymous e severidade ---------------------------------------------------------


def test_declared_anonymous_when_an_alternative_has_no_schemes() -> None:
    assert declared_anonymous(op("x", (SecurityRequirement(),)))
    assert declared_anonymous(op("x", (*BEARER, SecurityRequirement())))


def test_not_declared_anonymous_when_security_is_absent_or_required() -> None:
    assert not declared_anonymous(op("x", ()))
    assert not declared_anonymous(op("x", BEARER))
    assert not declared_anonymous(None)


def test_severity_is_high_when_the_openapi_requires_authentication() -> None:
    assert anonymous_severity(op("x", BEARER)) == "high"


def test_severity_is_medium_when_the_openapi_declares_no_security() -> None:
    assert anonymous_severity(op("x", ())) == "medium"
    assert anonymous_severity(None) == "medium"


def test_severity_is_medium_when_one_alternative_is_anonymous() -> None:
    assert anonymous_severity(op("x", (*BEARER, SecurityRequirement()))) == "medium"


# --- plano -------------------------------------------------------------------------------------


def test_plan_picks_one_get_per_operation_and_ignores_head_and_writes() -> None:
    items = [
        ex("a"),
        ex("a", target="/api/a?x=2"),
        ex("h", "HEAD"),
        ex("w", "POST"),
        ex("b", "PUT"),
    ]

    planned = plan(items)

    assert [t.operation_id for t in planned.tasks] == ["a"]
    assert planned.tasks[0].target == "/api/a"


def test_plan_without_any_get_says_no_read_exchange() -> None:
    planned = plan([ex("w", "POST")])

    assert planned.tasks == ()
    assert [n.reason for n in planned.not_tested] == ["no_read_exchange"]
    assert planned.not_tested[0].operation_id is None


def test_plan_marks_public_declared_and_infrastructure_operations() -> None:
    items = [
        ex("pub"),
        ex("anon"),
        ex("login", path="/auth/login"),
        ex("saude", path="/health"),
        ex("ok"),
    ]
    operations = {
        "pub": op("pub"),
        "anon": op("anon", (SecurityRequirement(),)),
        "login": op("login"),
        "saude": op("saude"),
        "ok": op("ok"),
    }

    planned = plan(
        items,
        operations,
        public=frozenset({"pub"}),
        infra=frozenset({"/auth/login", "/health"}),
    )

    assert [t.operation_id for t in planned.tasks] == ["ok"]
    assert reasons(planned) == {
        "pub": "public_operation",
        "anon": "declared_public",
        "login": "infrastructure_path",
        "saude": "infrastructure_path",
    }
    assert all(n.message for n in planned.not_tested)


def test_operation_without_security_is_tested_normally() -> None:
    planned = plan([ex("sem")], {"sem": op("sem", ())})

    assert [t.operation_id for t in planned.tasks] == ["sem"]


@pytest.mark.parametrize(
    ("check", "cap"),
    [("anonymous_access", MAX_ANONYMOUS_OPERATIONS), ("tampered_token", MAX_TAMPERED_OPERATIONS)],
)
def test_plan_caps_operations_and_reports_the_overflow(check: str, cap: int) -> None:
    items = [ex(f"o{i}") for i in range(cap + 5)]

    planned = plan(items, check=check)

    assert len(planned.tasks) == cap
    over = [n for n in planned.not_tested if n.reason == "budget_exhausted"]
    assert len(over) == 1
    assert "5" in over[0].message
    assert str(cap) in over[0].message
    assert over[0].check == check


def test_caps_are_the_ones_the_adr_decides() -> None:
    assert (MAX_ANONYMOUS_OPERATIONS, MAX_TAMPERED_OPERATIONS) == (200, 100)


# --- variantes: conclusão ---------------------------------------------------------------------


def test_any_equivalent_variant_is_a_finding_and_lists_only_the_accepted() -> None:
    results = [
        ("stripped_signature", "denied"),
        ("alg_none", "allowed_equivalent"),
        ("altered_claims", "allowed_equivalent"),
    ]

    assert conclude_variants(results) == "finding"  # type: ignore[arg-type]
    assert accepted_variants(results) == ("alg_none", "altered_claims")  # type: ignore[arg-type]


def test_all_denied_or_different_is_tested_without_finding() -> None:
    assert conclude_variants([("scrambled", "denied")]) == "tested"
    mixed = [("scrambled", "allowed_different"), ("alg_none", "denied")]
    assert conclude_variants(mixed) == "tested"  # type: ignore[arg-type]
    assert accepted_variants([("scrambled", "allowed_different")]) == ()


def test_a_server_error_without_acceptance_is_inconclusive_never_safe() -> None:
    assert conclude_variants([("scrambled", "denied"), ("alg_none", "error")]) == "inconclusive"
    assert conclude_variants([]) == "inconclusive"


def test_a_finding_wins_over_an_error_in_another_variant() -> None:
    results = [("alg_none", "error"), ("scrambled", "allowed_equivalent")]

    assert conclude_variants(results) == "finding"  # type: ignore[arg-type]


def test_cwe_is_347_when_a_jwt_variant_was_accepted_and_287_for_scrambled_only() -> None:
    assert tampered_cwe(("alg_none",)) == 347
    assert tampered_cwe(("scrambled", "altered_claims")) == 347
    assert tampered_cwe(("scrambled",)) == 287
