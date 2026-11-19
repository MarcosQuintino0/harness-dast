"""`report` com `nuclei.json` (ADR 0122): leitura, produto, gate e triagem pela fingerprint."""

import pytest

from harness_dast.application.report import ReportRequest
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.nuclei_result import NucleiResult
from tests.fakes.nuclei import nuclei_finding, nuclei_result
from tests.fakes.rig import agenda_flows
from tests.fakes.scan_rig import ScanRig


def scanned() -> ScanRig:
    rig = ScanRig(flows=agenda_flows())
    rig.run_probe()
    rig.run_scan()
    return rig


def request(rig: ScanRig, **changes: object) -> ReportRequest:
    return ReportRequest(product="agenda", run_id=rig.probe_result.run_id, **changes)  # type: ignore[arg-type]  # dict heterogêneo de teste


def stored(rig: ScanRig, severity: str = "high", product: str = "agenda") -> NucleiResult:
    run_id = rig.probe_result.run_id
    result = nuclei_result(
        findings=(nuclei_finding(severity=severity),), run_id=run_id, product=product
    )
    rig.artifacts.nuclei[run_id] = result
    return result


def test_report_reads_nuclei_json_and_carries_it_in_the_report() -> None:
    rig = scanned()
    result = stored(rig)

    outcome = rig.report().execute(request(rig))

    assert outcome.report.nuclei == result
    assert outcome.report.summary.nuclei_by_severity["high"] == 1


def test_report_without_nuclei_json_has_no_section_and_no_error() -> None:
    rig = scanned()

    outcome = rig.report().execute(request(rig))

    assert outcome.report.nuclei is None
    assert outcome.report.summary.nuclei_by_severity == {}


def test_a_nuclei_json_of_another_product_is_refused() -> None:
    rig = scanned()
    stored(rig, product="outro")

    with pytest.raises(ConfigError, match="outro produto"):
        rig.report().execute(request(rig))


def test_the_gate_counts_a_high_nuclei_finding_with_the_zap_quiet() -> None:
    rig = scanned()
    stored(rig, severity="critical")

    high = rig.report().execute(request(rig, fail_on="high"))
    none = rig.report().execute(request(rig, fail_on="none"))

    assert high.exceeds_threshold is True
    assert none.exceeds_threshold is False


def test_a_medium_nuclei_finding_does_not_reach_a_high_threshold() -> None:
    rig = scanned()
    stored(rig, severity="medium")

    outcome = rig.report().execute(request(rig, fail_on="high"))

    assert outcome.exceeds_threshold is False


def test_triage_matches_the_nuclei_finding_by_fingerprint_without_changing_it() -> None:
    rig = scanned()
    result = stored(rig)
    original = result.findings[0]
    rig.artifacts.triage[rig.probe_result.run_id] = {
        "schema_version": 1,
        "annotations": [
            {
                "fingerprint": original.fingerprint,
                "note": "endpoint de teste",
                "suspected_false_positive": True,
                "reason": "ambiente de homologação",
            }
        ],
    }

    outcome = rig.report().execute(request(rig))

    assert outcome.report.nuclei is not None
    merged = outcome.report.nuclei.findings[0]
    assert merged.triage is not None
    assert merged.triage.suspected_false_positive is True
    assert merged.triage.note == "endpoint de teste"
    assert merged.model_copy(update={"triage": None}) == original
    assert outcome.report.triage_orphans == ()


def test_a_triage_for_an_unknown_fingerprint_is_still_an_orphan() -> None:
    rig = scanned()
    stored(rig)
    rig.artifacts.triage[rig.probe_result.run_id] = {
        "schema_version": 1,
        "annotations": [{"fingerprint": "c" * 64, "note": "nada"}],
    }

    outcome = rig.report().execute(request(rig))

    assert outcome.report.triage_orphans == ("c" * 64,)
