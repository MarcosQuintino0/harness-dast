"""`scan` mede as regras do ZAP e `report`/`MetricsRecorder` gravam o `metrics.json` (ADR 0031)."""

from datetime import datetime, timedelta

from structlog.testing import capture_logs

from harness_dast.application.report import ReportRequest
from harness_dast.domain.errors import ConfigError, ExternalToolError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.rule_stats import RuleStat
from harness_dast.domain.run_summary import StageRecord
from harness_dast.domain.traffic import ProxyRow
from tests.fakes.rig import PASSWORD, TOKEN, agenda_flows, profile_data
from tests.fakes.scan_ports import FakeProxyAudit
from tests.fakes.scan_rig import ScanRig


def ready() -> ScanRig:
    rig = ScanRig(flows=agenda_flows())
    rig.run_probe()
    return rig


def run_id(rig: ScanRig) -> str:
    return rig.probe_result.run_id


# ---------------------------------------------------------------- o scan mede as regras


def test_scan_writes_the_rules_of_every_scanned_operation_and_the_zap_version() -> None:
    rig = ready()

    result = rig.run_scan()

    stats = rig.artifacts.rule_stats[run_id(rig)]
    assert [op.operation_id for op in stats.operations] == [e.operation_id for e in result.entries]
    assert all(len(op.rules) == 2 and op.unavailable_reason is None for op in stats.operations)
    assert stats.zap_version
    assert stats.operations[0].scan_id == result.entries[0].scan_id


def test_a_failure_reading_the_rules_does_not_fail_the_scan_and_is_logged_not_swallowed() -> None:
    rig = ready()
    rig.zap.failures = {"scan_rules": ExternalToolError("resposta inesperada do ZAP")}

    with capture_logs() as logs:
        result = rig.run_scan()

    assert result.status == "completed"
    assert [e.outcome for e in result.entries] == ["completed"] * 4
    stats = rig.artifacts.rule_stats[run_id(rig)]
    assert all(op.rules == () for op in stats.operations)
    assert all(op.unavailable_reason == "resposta inesperada do ZAP" for op in stats.operations)
    assert [log["event"] for log in logs].count("rule_stats_unavailable") == 4


def test_the_reason_of_an_unavailable_collection_is_cut_to_a_safe_size() -> None:
    rig = ready()
    rig.zap.failures = {"scan_rules": ExternalToolError("x" * 5000)}

    rig.run_scan()

    reasons = [op.unavailable_reason for op in rig.artifacts.rule_stats[run_id(rig)].operations]
    assert all(reason is not None and len(reason) <= 300 for reason in reasons)


def test_rules_are_collected_even_for_the_scan_the_cli_stopped() -> None:
    data = profile_data()
    data["limits"] = {**data["limits"], "max_duration_minutes": 1}
    rig = ScanRig(flows=agenda_flows(), profile=ProductProfile.from_data(data))
    rig.run_probe()
    rig.zap.script = [(10, "RUNNING")]

    result = rig.run_scan()

    assert result.status == "stopped_deadline"
    stats = rig.artifacts.rule_stats[run_id(rig)]
    assert [op.operation_id for op in stats.operations] == [e.operation_id for e in result.entries]
    assert stats.operations[-1].rules


def test_a_failed_write_of_rule_stats_does_not_fail_the_scan() -> None:
    rig = ready()

    rig.artifacts.failing_writes = {"rule_stats"}

    with capture_logs() as logs:
        result = rig.run_scan()

    assert result.status == "completed"
    assert "rule_stats_write_failed" in [log["event"] for log in logs]


# ---------------------------------------------------------------- report grava o arquivo


def scanned_with_rules(rules: tuple[RuleStat, ...] | None = None) -> ScanRig:
    rig = ready()
    if rules is not None:
        rig.zap.rule_stats = rules
    rig.run_scan()
    return rig


def test_report_writes_metrics_json_with_the_report_time_and_returns_the_file_name() -> None:
    rig = scanned_with_rules()

    outcome = rig.report(with_metrics=True).execute(
        ReportRequest(product="agenda", run_id=run_id(rig))
    )

    assert outcome.metrics_file == "metrics.json"
    metrics = rig.artifacts.metrics[run_id(rig)]
    assert metrics.stages_seconds.report is not None
    assert metrics.stages_seconds.scan is not None
    assert [op.operation_id for op in metrics.operations] == [
        "listar",
        "criar",
        "buscar",
        "atualizar",
    ]
    assert metrics.rules.totals[0].plugin_id == 40018
    assert metrics.rules.totals[0].operations == 4
    assert metrics.path_mode == "strict"


def test_report_without_a_recorder_writes_no_metrics() -> None:
    rig = scanned_with_rules()

    outcome = rig.report().execute(ReportRequest(product="agenda", run_id=run_id(rig)))

    assert outcome.metrics_file is None
    assert rig.artifacts.metrics == {}


def test_metrics_never_contain_the_token_the_password_or_a_url() -> None:
    rig = scanned_with_rules()
    rig.report(with_metrics=True).execute(ReportRequest(product="agenda", run_id=run_id(rig)))

    text = rig.artifacts.metrics[run_id(rig)].model_dump_json()

    assert TOKEN not in text
    assert PASSWORD not in text
    assert "http" not in text


# ---------------------------------------------------------------- o gravador nunca derruba


def test_recorder_returns_none_and_logs_when_the_run_has_no_manifest() -> None:
    rig = ScanRig()

    with capture_logs() as logs:
        written = rig.metrics_recorder().refresh("agenda", "2026-11-14T00-00-00Z-agenda-0000")

    assert written is None
    assert "metrics_not_written" in [log["event"] for log in logs]


def test_recorder_returns_none_when_the_write_fails() -> None:
    rig = scanned_with_rules()

    rig.artifacts.failing_writes = {"metrics"}

    with capture_logs() as logs:
        written = rig.metrics_recorder().refresh("agenda", run_id(rig))

    assert written is None
    assert "metrics_not_written" in [log["event"] for log in logs]


def test_recorder_measures_with_only_the_probe_when_there_is_no_scan() -> None:
    rig = ready()

    written = rig.metrics_recorder().refresh("agenda", run_id(rig))

    assert written == "metrics.json"
    metrics = rig.artifacts.metrics[run_id(rig)]
    assert metrics.operations == ()
    assert metrics.stages_seconds.scan is None
    assert metrics.stages_seconds.probe is not None


def test_a_broken_audit_only_removes_the_gaps_and_is_logged() -> None:
    rig = scanned_with_rules()
    audit = FakeProxyAudit(error=ConfigError("linha ilegível"))

    with capture_logs() as logs:
        written = rig.metrics_recorder(audit).refresh("agenda", run_id(rig))

    assert written == "metrics.json"
    assert rig.artifacts.metrics[run_id(rig)].traffic.gaps is None
    assert "metrics_audit_unavailable" in [log["event"] for log in logs]


def test_recorder_uses_the_run_stage_records_when_given() -> None:
    rig = scanned_with_rules()
    stages = (
        StageRecord(name="preflight", status="ok", duration_seconds=3.0),
        StageRecord(name="probe", status="ok", duration_seconds=7.0),
        StageRecord(name="scan", status="skipped"),
        StageRecord(name="authz", status="skipped"),
        StageRecord(name="report", status="not_run"),
    )

    rig.metrics_recorder().refresh(
        "agenda",
        run_id(rig),
        stages=stages,
        run_window=("2026-11-14T00:00:00", "2026-11-14T00:09:00"),
    )

    metrics = rig.artifacts.metrics[run_id(rig)]
    assert metrics.stages_seconds.preflight == 3.0
    assert metrics.stages_seconds.probe == 7.0
    assert metrics.stages_seconds.scan is None  # pulado no run: nunca zero nem o derivado
    assert metrics.finished_at == "2026-11-14T00:09:00"


def test_refreshing_twice_rewrites_the_same_content() -> None:
    rig = scanned_with_rules()
    recorder = rig.metrics_recorder()

    recorder.refresh("agenda", run_id(rig))
    first = rig.artifacts.metrics[run_id(rig)]
    recorder.refresh("agenda", run_id(rig))

    assert rig.artifacts.metrics[run_id(rig)] == first


def test_gaps_come_from_the_audit_rows_inside_the_scan_window() -> None:
    rig = scanned_with_rules()
    scan = rig.artifacts.scans[run_id(rig)]
    start = datetime.fromisoformat(scan.started_at)
    rows = tuple(
        ProxyRow(at=start + timedelta(seconds=s), decision="allow", reason="allowed", method="GET")
        for s in (0, 1, 40)
    )
    traffic = scan.traffic.model_copy(update={"enabled": True, "allowed": 3})
    rig.artifacts.scans[run_id(rig)] = scan.model_copy(
        update={"traffic": traffic, "finished_at": (start + timedelta(seconds=60)).isoformat()}
    )

    rig.metrics_recorder(FakeProxyAudit(rows)).refresh("agenda", run_id(rig))

    gaps = rig.artifacts.metrics[run_id(rig)].traffic.gaps
    assert gaps is not None
    assert (gaps.count, gaps.longest_seconds) == (1, 39.0)
