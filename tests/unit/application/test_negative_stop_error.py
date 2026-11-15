"""`negative_stop_error`: cada parada do estágio vira o código de saída certo; achado não é erro."""

import pytest

from harness_dast.application.stage_errors import negative_stop_error
from harness_dast.domain.errors import ExitCode
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_result import ProbeStatus


def result(status: ProbeStatus, message: str | None = None) -> NegativeResult:
    return NegativeResult(
        run_id="r1",
        product="demo",
        status=status,
        stop_message=message,
        started_at="2026-11-14T12:00:00+00:00",
        finished_at="2026-11-14T12:00:01+00:00",
    )


def test_a_completed_stage_has_no_error() -> None:
    assert negative_stop_error(result("completed")) is None


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("stopped_window", ExitCode.SCOPE),
        ("stopped_deadline", ExitCode.SCOPE),
        ("stopped_zap", ExitCode.EXTERNAL_TOOL),
        ("stopped_target_unresponsive", ExitCode.TARGET),
    ],
)
def test_each_stop_maps_to_its_exit_code(status: ProbeStatus, code: ExitCode) -> None:
    error = negative_stop_error(result(status, "parou aqui"))

    assert error is not None
    assert error.exit_code == code
    assert error.message == "parou aqui"
    assert error.hint


def test_the_default_message_names_the_stage() -> None:
    error = negative_stop_error(result("stopped_window"))

    assert error is not None
    assert "negative" in error.message
