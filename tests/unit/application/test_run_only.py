"""`run --only` (ADR 0112): a seleção só reduz e chega ao probe, ao scan e ao negative."""

import pytest
from pydantic import ValidationError

from harness_dast.application.run import RunRequest
from harness_dast.domain.errors import ConfigError, ExitCode
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.run_summary import RunOptions
from tests.unit.application.test_run import Rig
from tests.unit.application.test_run_negative import Rig as NegativeRig


def test_run_passes_only_to_probe_scan_and_negative_and_records_it() -> None:
    rig = NegativeRig()

    result = rig.run(RunRequest(product="demo", only=("getPet", "listPets")))

    assert [request.only for request in rig.negative_requests] == [("getPet", "listPets")]
    assert result.summary.options.only == ("getPet", "listPets")


def test_run_passes_only_to_probe_and_scan() -> None:
    rig = Rig()

    rig.run(RunRequest(product="demo", authz=False, negative=False, only=("getPet",)))

    assert [request.only for request in rig.probe_requests] == [("getPet",)]
    assert [request.only for request in rig.scan_requests] == [("getPet",)]


def test_run_without_only_keeps_every_operation() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", authz=False, negative=False))

    assert rig.probe_requests[0].only == ()
    assert rig.scan_requests[0].only == ()
    assert result.summary.options.only == ()


def test_run_with_unknown_operation_stops_as_usage_error_before_the_scan() -> None:
    def unknown() -> ProbeResult:
        raise ConfigError("Operação desconhecida: nope.", hint="Use um operation_id do OpenAPI.")

    rig = Rig(probe=unknown)

    result = rig.run(RunRequest(product="demo", authz=False, negative=False, only=("nope",)))

    assert result.summary.exit_code == int(ExitCode.USAGE)
    assert rig.calls == ["preflight", "probe"]


def test_an_old_run_json_without_only_reads_as_all_operations() -> None:
    assert RunOptions.model_validate({"seed": 1}).only == ()


def test_run_options_reject_a_malformed_only() -> None:
    with pytest.raises(ValidationError):
        RunOptions.model_validate({"only": "getPet"})
