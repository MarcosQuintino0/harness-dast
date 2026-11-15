"""Plano do scan para operações de envio de arquivo (ADR 0052, seção 4)."""

import pytest

from harness_dast.domain import scan_plan
from harness_dast.domain.api_model import MediaBody, Operation, RequestBody
from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.scan_config import ScanConfig
from harness_dast.domain.scan_plan import (
    ScanPlan,
    last_sent,
    multipart_operation_ids,
    resolve_targets,
    select_candidates,
)
from harness_dast.domain.scope import Scope, ScopeGuard
from harness_dast.domain.zap_messages import LearnedRequest
from tests.unit.domain.report_helpers import operation
from tests.unit.domain.test_scan_domain import audit_result

GUARD = ScopeGuard(
    Scope.model_validate(
        {
            "allow": [
                {
                    "host": "alvo",
                    "scheme": "http",
                    "paths": ["/**"],
                    "methods": ["GET", "POST"],
                    "allow_local": True,
                }
            ]
        }
    )
)
UPLOAD = frozenset({"enviar"})


@pytest.fixture(autouse=True)
def _zap_can_scan_multipart(monkeypatch: pytest.MonkeyPatch) -> None:
    """Os testes de plano partem de um ZAP que varre multipart; o padrão real é testado à parte."""
    monkeypatch.setattr(scan_plan, "MULTIPART_SCANNABLE", True)


def _spec_op(operation_id: str, *media_types: str) -> Operation:
    body = RequestBody(media=tuple(MediaBody(media_type=item) for item in media_types))
    return Operation.model_validate(
        {
            "operation_id": operation_id,
            "method": "post",
            "path": f"/{operation_id}",
            "request_body": body.model_dump(),
        }
    )


def _select(
    config: ScanConfig, uploads: frozenset[str] = UPLOAD, outcome: str = "success"
) -> tuple[tuple[str, ...], dict[str, str]]:
    ops = [operation("enviar", "POST", "/enviar", outcome), operation("criar", "POST", "/criar")]
    sent = {
        "enviar": last_sent([audit_result(1, "enviar", "POST", "/enviar", 201)])["enviar"],
        "criar": last_sent([audit_result(2, "criar", "POST", "/criar", 201)])["criar"],
    }
    planned = {
        item.operation_id: PlannedOperation(
            operation_id=item.operation_id, method="POST", path=item.path, decision="send"
        )
        for item in ops
    }
    candidates, skipped = select_candidates(
        ops,
        planned,
        sent,
        login_path=None,
        config=config,
        include_outcomes=frozenset({"validation_error"}),
        uploads=uploads,
    )
    return (
        tuple(item.result.operation_id for item in candidates),
        {item.operation_id: item.reason for item in skipped},
    )


def test_upload_operation_is_not_scanned_without_the_letter_permission() -> None:
    chosen, skipped = _select(ScanConfig())

    assert chosen == ("criar",)
    assert skipped == {"enviar": "upload_scan_not_authorized"}


def test_upload_operation_is_a_candidate_with_the_permission() -> None:
    chosen, skipped = _select(ScanConfig(allow_upload_scan=True))

    assert chosen == ("enviar", "criar")
    assert skipped == {}


def test_a_non_upload_operation_is_not_affected_by_the_permission_being_off() -> None:
    chosen, skipped = _select(ScanConfig(), uploads=frozenset())

    assert chosen == ("enviar", "criar")
    assert skipped == {}


def test_with_the_permission_but_an_unscannable_multipart_the_reason_is_multipart_not_scannable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scan_plan, "MULTIPART_SCANNABLE", False)

    chosen, skipped = _select(ScanConfig(allow_upload_scan=True))

    assert chosen == ("criar",)
    assert skipped == {"enviar": "multipart_not_scannable"}


def test_without_the_permission_the_authorization_reason_comes_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scan_plan, "MULTIPART_SCANNABLE", False)

    _, skipped = _select(ScanConfig())

    assert skipped == {"enviar": "upload_scan_not_authorized"}


def test_a_probe_class_that_is_not_allowed_keeps_the_older_reason_for_uploads() -> None:
    chosen, skipped = _select(ScanConfig(allow_upload_scan=True), outcome="server_error")

    assert chosen == ("criar",)
    assert skipped == {"enviar": "not_success"}


def _plan(body: str | None, uploads: frozenset[str]) -> ScanPlan:
    ops = [operation("enviar", "POST", "/enviar")]
    sent = {"enviar": last_sent([audit_result(1, "enviar", "POST", "/enviar", 201)])["enviar"]}
    planned = {
        "enviar": PlannedOperation(
            operation_id="enviar", method="POST", path="/enviar", decision="send"
        )
    }
    candidates, _ = select_candidates(
        ops, planned, sent, login_path=None, config=ScanConfig(allow_upload_scan=True)
    )
    learned = [
        LearnedRequest(message_id=5, method="POST", url="http://alvo/enviar", body=body, status=201)
    ]
    return resolve_targets(candidates, sent, learned, GUARD, uploads)


def test_a_multipart_body_with_only_ascii_is_scanned_with_the_learned_body() -> None:
    plan = _plan("--b\r\nContent-Disposition: form-data; name=a\r\n\r\nx\r\n--b--\r\n", UPLOAD)

    assert [t.operation_id for t in plan.targets] == ["enviar"]
    assert plan.skipped == ()


def test_a_multipart_body_with_non_ascii_bytes_is_reached_but_not_scanned() -> None:
    plan = _plan("--b\r\n\r\n\x89PNG\r\n\x1a\n�\r\n--b--\r\n", UPLOAD)

    assert plan.targets == ()
    assert [(s.operation_id, s.reason) for s in plan.skipped] == [("enviar", "binary_body")]
    assert "synthetic_file" in plan.skipped[0].message


def test_a_non_ascii_json_body_on_a_non_upload_operation_is_still_scanned() -> None:
    plan = _plan('{"nome": "ação"}', frozenset())

    assert [t.operation_id for t in plan.targets] == ["enviar"]


def test_an_upload_without_a_learned_body_is_scanned_as_empty_not_crashing() -> None:
    plan = _plan(None, UPLOAD)

    assert [t.body for t in plan.targets] == [None]


def test_multipart_operations_are_found_by_the_preferred_media_type() -> None:
    operations = [
        _spec_op("a", "multipart/form-data"),
        _spec_op("b", "application/json", "multipart/form-data"),
        _spec_op("c", "Multipart/Form-Data; boundary=x"),
        _spec_op("d", "application/x-www-form-urlencoded"),
        Operation.model_validate({"operation_id": "e", "method": "get", "path": "/e"}),
    ]

    assert multipart_operation_ids(operations) == {"a", "c"}


def test_no_operations_gives_no_upload_ids() -> None:
    assert multipart_operation_ids([]) == frozenset()
