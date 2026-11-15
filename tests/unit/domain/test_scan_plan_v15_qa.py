"""QA independente (V1.5c): o plano do scan com classes extras e métodos adulterados."""

import pytest

from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.scan_config import EXTRA_OUTCOMES, ScanConfig
from harness_dast.domain.scan_plan import last_sent, select_candidates
from tests.unit.domain.report_helpers import operation
from tests.unit.domain.test_scan_domain import audit_result

ALL_CLASSES = ("not_found", "conflict", "validation_error", "client_error", "logical_failure")


def _plan(method: str, outcome: str, *, include: frozenset[str]) -> tuple[list[str], list[str]]:
    ops = [operation("alvo", method, "/alvo", outcome)]
    sent = {"alvo": last_sent([audit_result(1, "alvo", method, "/alvo", 404)])["alvo"]}
    planned = {
        "alvo": PlannedOperation(operation_id="alvo", method=method, path="/alvo", decision="send")
    }
    candidates, skipped = select_candidates(
        ops, planned, sent, login_path=None, config=ScanConfig(), include_outcomes=include
    )
    return [c.result.operation_id for c in candidates], [s.reason for s in skipped]


@pytest.mark.parametrize("outcome", ALL_CLASSES)
def test_delete_is_never_a_candidate_whatever_the_seed_class(outcome: str) -> None:
    chosen, reasons = _plan("DELETE", outcome, include=frozenset(EXTRA_OUTCOMES))

    assert chosen == []
    assert reasons == ["delete"]


@pytest.mark.parametrize(
    "outcome",
    ["server_error", "auth_error", "csrf_error", "rate_limited", "redirect", "skipped_scope"],
)
def test_classes_outside_the_closed_list_are_never_seeds_even_if_asked(outcome: str) -> None:
    chosen, reasons = _plan("GET", outcome, include=frozenset({*EXTRA_OUTCOMES, outcome}))

    assert chosen == []
    assert reasons == ["not_success"]


@pytest.mark.parametrize("outcome", ALL_CLASSES)
def test_a_class_not_asked_for_is_not_a_seed(outcome: str) -> None:
    chosen, reasons = _plan("GET", outcome, include=frozenset(EXTRA_OUTCOMES) - {outcome})

    assert chosen == []
    assert reasons == ["not_success"]


@pytest.mark.parametrize("method", ["delete", "Delete", "dELETE"])
@pytest.mark.xfail(
    strict=True,
    reason="QA V1.5c: scan_plan._decide compara result.method == 'DELETE' sem normalizar; "
    "um probe.json com método em minúsculas (adulterado ou de outro gerador) vira candidato de "
    "varredura de DELETE",
)
def test_delete_with_a_non_uppercase_method_is_still_never_scanned(method: str) -> None:
    chosen, _ = _plan(method, "success", include=frozenset())

    assert chosen == []


@pytest.mark.parametrize("method", ["put", "patch", "Put"])
@pytest.mark.xfail(
    strict=True,
    reason="QA V1.5c: scan_plan._decide só aplica a regra 'PUT/PATCH só sobre recurso criado' "
    "com método em maiúsculas; em minúsculas o PUT/PATCH passa sem scan.mutating_methods",
)
def test_a_lowercase_put_or_patch_still_needs_a_resource_created_by_the_run(method: str) -> None:
    chosen, _ = _plan(method, "success", include=frozenset())

    assert chosen == []
