"""`report` com `negative.json` (ADR 0051): leitura, gate, produto e janela dos sinais da cerca."""

from datetime import timedelta

import pytest

from harness_dast.application.report import ReportRequest
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.signal_findings import parse_instant
from harness_dast.domain.traffic import ProxyRow
from tests.fakes.rig import agenda_flows
from tests.fakes.scan_ports import FakeProxyAudit
from tests.fakes.scan_rig import ScanRig
from tests.unit.domain.negative_samples import accepted, negative_result


def scanned() -> ScanRig:
    rig = ScanRig(flows=agenda_flows())
    rig.run_probe()
    rig.run_scan()
    return rig


def request(rig: ScanRig, **changes: object) -> ReportRequest:
    return ReportRequest(product="agenda", run_id=rig.probe_result.run_id, **changes)  # type: ignore[arg-type]  # dict heterogêneo de teste


def stored(rig: ScanRig, **changes: object) -> NegativeResult:
    run_id = rig.probe_result.run_id
    result = negative_result(product="agenda", run_id=run_id).model_copy(update=changes)
    rig.artifacts.negative[run_id] = result
    return result


def test_report_reads_negative_json_and_carries_it_in_the_report() -> None:
    rig = scanned()
    result = stored(rig)

    outcome = rig.report().execute(request(rig))

    assert outcome.report.negative == result
    assert outcome.report.summary.negative_by_severity["low"] == 2
    assert outcome.report.summary.total == 0


def test_report_without_negative_json_has_no_section_and_no_error() -> None:
    rig = scanned()

    outcome = rig.report().execute(request(rig))

    assert outcome.report.negative is None
    assert outcome.report.summary.negative_by_severity == {}


def test_a_negative_json_of_another_product_is_refused() -> None:
    rig = scanned()
    stored(rig, product="outro")

    with pytest.raises(ConfigError, match="outro produto"):
        rig.report().execute(request(rig))


def test_the_gate_counts_a_negative_finding_with_the_zap_quiet() -> None:
    rig = scanned()
    stored(rig, findings=(accepted(severity="medium"),))

    medium = rig.report().execute(request(rig, fail_on="medium"))
    high = rig.report().execute(request(rig, fail_on="high"))

    assert medium.exceeds_threshold is True
    assert high.exceeds_threshold is False


def _late_rows(rig: ScanRig, finished: str) -> tuple[ProxyRow, ...]:
    end = parse_instant(finished)
    assert end is not None
    return tuple(
        ProxyRow(
            at=end - timedelta(minutes=1),
            decision="allow",
            reason="allowed",
            method="GET",
            path=f"/api/pacientes/{number}",
            status=500,
            signals=("sql_error",),
        )
        for number in (7, 8)
    )


def _run_end(rig: ScanRig) -> str:
    probe = rig.probe_result.finished_at
    scan = rig.artifacts.scans[rig.probe_result.run_id].finished_at
    moments = [parse_instant(text) for text in (probe, scan)]
    return max(moment for moment in moments if moment is not None).isoformat()


def test_the_fence_window_includes_the_end_of_the_negative_stage() -> None:
    rig = scanned()
    late = parse_instant(_run_end(rig))
    assert late is not None
    finished = (late + timedelta(minutes=30)).isoformat()
    rows = _late_rows(rig, finished)

    before = rig.report(proxy_audit=FakeProxyAudit(rows)).execute(request(rig))
    stored(rig, finished_at=finished)
    after = rig.report(proxy_audit=FakeProxyAudit(rows)).execute(request(rig))

    assert before.report.proxy_signals is not None
    assert before.report.proxy_signals.responses_examined == 0
    assert after.report.proxy_signals is not None
    assert after.report.proxy_signals.responses_examined == 2
    assert after.report.proxy_signals.counts["sql_error"] == 2
