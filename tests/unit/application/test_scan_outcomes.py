"""`scan` com `scan.include_outcomes`: o perfil decide, a flag só escolhe dentro dele (ADR 0050)."""

from typing import Any

import pytest

from harness_dast.application.scan import ScanRequest
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.scan_result import ScanResult
from tests.fakes.probe_ports import reply
from tests.fakes.rig import agenda_flows, agenda_profile, default_handler
from tests.fakes.scan_rig import ScanRig


def _handler(request: Any, jar: dict[str, str]) -> Any:
    """`buscar` (GET /api/pacientes/{id}) responde 404; o resto é o alvo bem-comportado."""
    path = request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
    if request.method == "GET" and path.startswith("api/pacientes/"):
        return reply(404, {"detail": "nao existe"})
    return default_handler(request, jar)


def _rig(*outcomes: str) -> ScanRig:
    profile = agenda_profile(scan={"include_outcomes": list(outcomes)})
    rig = ScanRig(profile=profile, flows=agenda_flows(), handler=_handler)
    rig.run_probe()
    return rig


def _reasons(result: ScanResult) -> dict[str, str]:
    return {item.operation_id: item.reason for item in result.skipped}


def test_without_the_list_the_not_found_operation_stays_out_as_not_success() -> None:
    rig = _rig()

    result = rig.run_scan()

    assert next(o for o in rig.probe_result.operations if o.operation_id == "buscar").outcome == (
        "not_found"
    )
    assert _reasons(result)["buscar"] == "not_success"
    assert result.include_outcomes == ()
    assert all(item.seed_outcome is None for item in result.entries)


def test_without_a_flag_the_profile_list_applies_and_marks_the_seed() -> None:
    rig = _rig("not_found")

    result = rig.run_scan()

    entry = next(item for item in result.entries if item.operation_id == "buscar")
    assert entry.seed_outcome == "not_found"
    assert result.include_outcomes == ("not_found",)
    assert all(item.seed_outcome is None for item in result.entries if item is not entry)


def test_a_class_in_the_list_does_not_include_other_classes() -> None:
    rig = _rig("validation_error")

    result = rig.run_scan()

    assert _reasons(result)["buscar"] == "not_success"


def test_the_dry_run_shows_the_seed_outcome_in_the_plan() -> None:
    rig = _rig("not_found")

    result = rig.run_scan(dry_run=True)

    planned = {item.operation_id: item.seed_outcome for item in result.planned}
    assert planned["buscar"] == "not_found"
    assert planned["listar"] is None
    assert rig.zap.started == []


def test_a_flag_inside_the_profile_list_reduces_to_that_class() -> None:
    rig = _rig("not_found", "conflict")

    result = rig.run_scan(include_outcomes=("not_found",))

    assert result.include_outcomes == ("not_found",)
    assert "buscar" in [item.operation_id for item in result.entries]


def test_an_empty_choice_reduces_to_success_only() -> None:
    rig = _rig("not_found")

    result = rig.run_scan(include_outcomes=())

    assert result.include_outcomes == ()
    assert _reasons(result)["buscar"] == "not_success"


def test_a_flag_outside_the_profile_list_is_refused_and_nothing_is_sent() -> None:
    rig = _rig("not_found")

    with pytest.raises(ConfigError, match="não lista"):
        rig.run_scan(include_outcomes=("validation_error",))

    assert rig.zap.started == []


def test_a_flag_with_an_empty_profile_list_is_refused() -> None:
    rig = _rig()

    with pytest.raises(ConfigError, match="não lista"):
        rig.run_scan(include_outcomes=("not_found",))

    assert rig.zap.started == []


@pytest.mark.parametrize("name", ["server_error", "auth_error", "success", "", "NOT_FOUND"])
def test_a_class_outside_the_closed_list_is_refused_even_with_the_profile_listing_others(
    name: str,
) -> None:
    rig = _rig("not_found")

    with pytest.raises(ConfigError, match="include-outcome"):
        rig.run_scan(include_outcomes=(name,))


def test_delete_and_login_stay_out_even_when_their_class_is_included() -> None:
    rig = _rig("not_found", "validation_error", "conflict", "client_error", "logical_failure")
    rig.run_probe(include_delete=True)

    result = rig.run_scan()

    reasons = _reasons(result)
    assert reasons["login"] == "login"
    assert reasons["remover"] == "delete"
    assert "DELETE" not in [item.method for item in rig.zap.started]


def test_the_request_default_means_the_profile_list() -> None:
    assert ScanRequest(product="agenda", run_id="x").include_outcomes is None
