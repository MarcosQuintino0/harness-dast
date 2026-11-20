"""`run` e as classes extras da varredura (ADR 0050): o perfil decide, a flag só reduz."""

from harness_dast.application.run import RunRequest
from tests.unit.application.test_run import Rig


def test_run_passes_no_override_so_the_scan_uses_the_profile_list() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", authz=False, negative=False))

    assert rig.scan_requests[0].include_outcomes is None
    assert result.summary.options.include_outcomes is True


def test_run_without_include_outcomes_reduces_the_scan_to_success_only() -> None:
    rig = Rig()

    result = rig.run(
        RunRequest(product="demo", authz=False, negative=False, include_outcomes=False)
    )

    assert rig.scan_requests[0].include_outcomes == ()
    assert result.summary.options.include_outcomes is False


def test_an_old_run_json_without_the_option_still_reads_as_the_default() -> None:
    from harness_dast.domain.run_summary import RunOptions

    assert RunOptions.model_validate({"seed": 1}).include_outcomes is True
