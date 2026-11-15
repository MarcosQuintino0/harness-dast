"""`scan` de operação de envio de arquivo: só com `scan.allow_upload_scan` da carta (ADR 0052)."""

from typing import Any

import pytest

from harness_dast.domain import scan_plan
from harness_dast.domain.api_model import MediaBody, Operation, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.scan_result import ScanResult
from tests.fakes.rig import agenda_flows, agenda_profile, agenda_spec
from tests.fakes.scan_rig import ScanRig


def _spec() -> Any:
    spec = agenda_spec()
    schema = Schema(
        type="object",
        properties={
            "arquivo": Schema(type="string", format="binary"),
            "descricao": Schema(type="string"),
        },
        required=("arquivo",),
    )
    upload = Operation(
        operation_id="enviar",
        method="post",
        path="/api/documentos",
        request_body=RequestBody(
            required=True,
            media=(MediaBody(media_type="multipart/form-data", body_schema=schema),),
        ),
    )
    return spec.model_copy(update={"operations": (*spec.operations, upload)})


@pytest.fixture
def zap_scans_multipart(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_plan, "MULTIPART_SCANNABLE", True)


def _rig(**scan: Any) -> ScanRig:
    profile = agenda_profile(scan=scan)
    rig = ScanRig(profile=profile, flows=agenda_flows(), spec=_spec())
    rig.run_probe()
    return rig


def _reasons(result: ScanResult) -> dict[str, str]:
    return {item.operation_id: item.reason for item in result.skipped}


def test_the_probe_reaches_the_upload_operation_with_a_multipart_body() -> None:
    rig = _rig()

    sent = next(item for item in rig.probe_result.operations if item.operation_id == "enviar")

    assert sent.outcome == "success"


def test_without_the_permission_the_upload_is_reached_but_not_scanned() -> None:
    rig = _rig()

    result = rig.run_scan(dry_run=True)

    assert _reasons(result)["enviar"] == "upload_scan_not_authorized"
    assert "enviar" not in [item.operation_id for item in result.planned]
    assert "criar" in [item.operation_id for item in result.planned]


def test_with_the_permission_the_upload_goes_into_the_plan(zap_scans_multipart: None) -> None:
    rig = _rig(allow_upload_scan=True)

    result = rig.run_scan(dry_run=True)

    assert "enviar" not in _reasons(result)
    assert "enviar" in [item.operation_id for item in result.planned]


def test_with_the_permission_the_live_scan_runs_the_upload_with_the_learned_multipart_body(
    zap_scans_multipart: None,
) -> None:
    rig = _rig(allow_upload_scan=True)

    result = rig.run_scan()

    assert "enviar" in [item.operation_id for item in result.entries]
    assert "enviar" not in _reasons(result)


def test_the_scan_flag_only_selecting_the_upload_does_not_override_the_missing_permission() -> None:
    rig = _rig()

    result = rig.run_scan(only=("enviar",))

    assert _reasons(result)["enviar"] == "upload_scan_not_authorized"
    assert result.entries == ()


def test_with_the_permission_but_the_committed_zap_decision_the_upload_is_not_scannable() -> None:
    rig = _rig(allow_upload_scan=True)

    result = rig.run_scan()

    assert _reasons(result)["enviar"] == "multipart_not_scannable"
    assert "enviar" not in [item.operation_id for item in result.entries]
    assert "enviar" not in [item.operation_id for item in result.planned]


def test_the_committed_decision_is_that_the_zap_cannot_scan_multipart() -> None:
    assert scan_plan.MULTIPART_SCANNABLE is False
