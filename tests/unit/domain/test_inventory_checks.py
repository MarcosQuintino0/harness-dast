"""Inventário: versões irmãs com controle, documentação exposta, cerca e teto (ADR 0102)."""

import pytest

from harness_dast.domain.api_model import Operation
from harness_dast.domain.inventory_checks import (
    CONTROL_VERSION,
    DOC_PATHS,
    INVENTORY_MAX_REQUESTS,
    SIBLING_MAX_FAMILIES,
    candidate_numbers,
    doc_text,
    docs_alert,
    judge_sibling,
    plan_inventory,
    read_docs,
    sibling_alert,
)
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.zap_alert import RawAlert


def op(operation_id: str, path: str, method: str = "get") -> Operation:
    return Operation(operation_id=operation_id, method=method, path=path)  # type: ignore[arg-type]


def allow_all(method: str, target: str) -> bool:
    return True


def test_candidate_numbers_try_previous_next_and_two_back() -> None:
    assert candidate_numbers(3) == (2, 4, 1)
    assert candidate_numbers(1) == (2,)


def test_a_versioned_operation_gets_a_control_and_only_undocumented_siblings() -> None:
    operations = {"v3": op("v3", "/api/v3/items"), "v2": op("v2", "/api/v2/items")}

    plan = plan_inventory(operations, [], permits=allow_all)

    by_op = {family.operation_id: family for family in plan.families}
    assert by_op["v3"].siblings == ("/api/v4/items", "/api/v1/items")  # v2 está no contrato
    assert by_op["v3"].control == f"/api/v{CONTROL_VERSION}/items"
    assert by_op["v2"].siblings == ("/api/v1/items",)  # v3 também está no contrato


def test_siblings_documented_in_the_contract_are_never_probed() -> None:
    operations = {"a": op("a", "/x/v1/y"), "b": op("b", "/x/v2/y")}

    plan = plan_inventory(operations, [], permits=allow_all)

    targets = {t for family in plan.families for t in family.siblings}
    assert not {"/x/v1/y", "/x/v2/y"} & targets
    assert "/x/v3/y" in targets


def test_what_the_fence_denies_is_reported_not_sent() -> None:
    operations = {"v3": op("v3", "/api/v3/items")}

    plan = plan_inventory(operations, [], permits=lambda m, t: t.startswith("/api/v4"))

    assert plan.families == ()  # o controle (v999) foi negado: sem controle não se testa
    assert plan.docs == ()
    reasons = {s.reason for s in plan.skipped}
    assert reasons == {"not_verifiable_by_fence"}


def test_a_template_with_a_parameter_uses_the_concrete_target_of_the_probe() -> None:
    operations = {"g": op("g", "/api/v2/items/{id}")}
    exchange = ExchangeRecord(
        operation_id="g",
        method="GET",
        path="/api/v2/items/{id}",
        target="/api/v2/items/7?x=1",
        account="u",
        status=200,
    )

    with_example = plan_inventory(operations, [exchange], permits=allow_all)
    without = plan_inventory(operations, [], permits=allow_all)

    assert with_example.families[0].siblings[0] == "/api/v1/items/7"
    assert without.families == ()
    assert [s.reason for s in without.skipped] == ["needs_example"]


def test_the_docs_list_is_fixed_and_skips_what_the_contract_documents() -> None:
    plan = plan_inventory({"d": op("d", "/docs")}, [], permits=allow_all)

    assert "/docs" not in plan.docs
    assert "/openapi.json" in plan.docs
    assert set(plan.docs) <= set(DOC_PATHS)


def test_the_hard_cap_bounds_the_requests() -> None:
    operations = {f"o{i}": op(f"o{i}", f"/s{i}/v5/x") for i in range(10)}

    plan = plan_inventory(operations, [], permits=allow_all, max_requests=500)

    sent = sum(1 + len(f.siblings) for f in plan.families) + len(plan.docs)
    assert sent <= INVENTORY_MAX_REQUESTS
    assert len(plan.families) <= SIBLING_MAX_FAMILIES
    assert any(s.reason == "budget_exceeded" for s in plan.skipped)


def test_only_narrows_the_siblings_but_not_the_docs() -> None:
    operations = {"a": op("a", "/a/v3/x"), "b": op("b", "/b/v3/x")}

    plan = plan_inventory(operations, [], permits=allow_all, only=frozenset({"a"}))

    assert [f.operation_id for f in plan.families] == ["a"]
    assert plan.docs


@pytest.mark.parametrize(
    ("status", "control", "verdict"),
    [
        (200, 404, "exists"),
        (401, 404, "exists"),
        (405, 404, "exists"),
        (404, 404, "absent"),
        (410, 401, "absent"),
        (200, 200, "unclear"),
        (401, 401, "unclear"),
        (None, 404, "unclear"),
        (200, None, "exists"),
    ],
)
def test_judge_sibling_compares_with_the_control(
    status: int | None, control: int | None, verdict: str
) -> None:
    assert judge_sibling(status, control) == verdict


def test_only_a_200_with_documentation_marks_is_exposure() -> None:
    assert read_docs(200, '{"openapi":"3.0.1"}') is not None
    assert read_docs(200, '{"openapi":"3.0.1"}').kind == "spec"  # type: ignore[union-attr]
    assert read_docs(200, "<html>SwaggerUI bundle</html>").kind == "ui"  # type: ignore[union-attr]
    assert read_docs(200, "<html>qualquer pagina</html>") is None
    assert read_docs(404, '{"openapi":"3"}') is None


def test_doc_text_is_bounded_and_tolerates_bad_bytes() -> None:
    assert doc_text(b"\xff\xfeabc").endswith("abc")
    assert len(doc_text(b"a" * 200_000)) == 65536


def test_the_alerts_are_low_or_informational_and_valid() -> None:
    reading = read_docs(200, '{"swagger":"2.0"}')
    assert reading is not None
    docs = docs_alert(1, "/swagger.json", reading, base_url="http://crapi")
    live = sibling_alert(1, "v3", "/api/v2/items", 200, base_url="http://crapi")
    guarded = sibling_alert(2, "v3", "/api/v2/items", 401, base_url="http://crapi")

    for alert in (docs, live, guarded):
        RawAlert.model_validate(alert)
    assert (docs["risk"], live["risk"], guarded["risk"]) == ("Low", "Low", "Informational")
