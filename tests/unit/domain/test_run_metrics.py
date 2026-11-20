"""`domain.run_metrics`: o `metrics.json` montado do que a execução já gravou (ADR 0031)."""

from datetime import UTC, datetime, timedelta

from harness_dast.domain.probe_result import ArtifactHashes, RunManifest
from harness_dast.domain.rule_stats import OperationRules, RuleStat, RuleStatsFile
from harness_dast.domain.run import RunLimits
from harness_dast.domain.run_metrics import RunMetrics, build_run_metrics
from harness_dast.domain.run_summary import StageRecord
from harness_dast.domain.scan_result import ScanResult
from harness_dast.domain.traffic import ProxyRow, TrafficSummary
from tests.unit.domain.report.helpers import RUN_ID, entry, operation, probe_result, scan_result

SCAN_START = datetime(2026, 11, 13, 5, 16, 10, tzinfo=UTC)  # igual a scan_result()


def manifest() -> RunManifest:
    return RunManifest(
        run_id=RUN_ID,
        command="probe",
        product="vampi",
        harness_version="1.1.0",
        zap_version="2.17.0",
        hashes=ArtifactHashes(target_yml="a" * 64),
        limits=RunLimits(requests_per_second=5, max_duration_minutes=60, zap_threads_per_host=2),
        seed=1,
        started_at="2026-11-13T05:15:30+00:00",
    )


def rule(plugin_id: int, time_ms: int | None = 100, state: str = "completed") -> RuleStat:
    return RuleStat.model_validate(
        {
            "plugin_id": plugin_id,
            "name": f"Regra {plugin_id}",
            "state": state,
            "time_ms": time_ms,
            "requests": 4,
            "alerts": 1,
        }
    )


def scan(**changes: object) -> ScanResult:
    base = scan_result([entry("listar", "GET", "/users/v1", 1)])
    return base.model_copy(update=changes) if changes else base


def build(**changes: object) -> RunMetrics:
    arguments: dict[str, object] = {
        "manifest": manifest(),
        "probe": probe_result([operation("listar", "GET", "/users/v1")]),
        "scan": scan(),
        "authz": None,
        "rule_stats": None,
        "proxy_rows": None,
        "stages": None,
        "run_window": None,
        "report_seconds": None,
        "path_mode": "strict",
        "harness_version": "1.1.0",
        "generated_at": "2026-11-13T05:30:00+00:00",
    }
    return build_run_metrics(**{**arguments, **changes})  # type: ignore[arg-type]  # dict heterogêneo de teste


def stats(*operations: OperationRules) -> RuleStatsFile:
    return RuleStatsFile(run_id=RUN_ID, zap_version="2.17.0", operations=operations)


def row(offset: float, decision: str = "allow") -> ProxyRow:
    return ProxyRow(
        at=SCAN_START + timedelta(seconds=offset), decision=decision, reason="x", method="GET"
    )


# ---------------------------------------------------------------- identificação e etapas


def test_identity_comes_from_the_manifest_the_profile_mode_and_the_injected_clock() -> None:
    metrics = build(path_mode="wide")

    assert (metrics.run_id, metrics.product, metrics.path_mode) == (RUN_ID, "vampi", "wide")
    assert metrics.harness_version == "1.1.0"
    assert metrics.zap_version == "2.17.0"
    assert metrics.generated_at == "2026-11-13T05:30:00+00:00"
    assert metrics.schema_version == 1


def test_the_zap_version_of_the_scan_wins_over_the_one_of_the_manifest() -> None:
    other = RuleStatsFile(run_id=RUN_ID, zap_version="2.18.0")

    assert build(rule_stats=other).zap_version == "2.18.0"


def test_stage_times_come_from_each_stage_file_and_a_stage_that_did_not_run_is_none() -> None:
    metrics = build(report_seconds=1.5)

    seconds = metrics.stages_seconds
    assert seconds.probe == 28.0
    assert seconds.scan == 230.0
    assert seconds.report == 1.5
    assert seconds.preflight is None
    assert seconds.authz is None


def test_a_dry_run_scan_or_probe_is_not_a_measured_stage() -> None:
    dry_scan = scan(dry_run=True)
    dry_probe = probe_result([operation("a", "GET", "/a")]).model_copy(update={"dry_run": True})

    metrics = build(scan=dry_scan, probe=dry_probe)

    assert metrics.stages_seconds.scan is None
    assert metrics.stages_seconds.probe is None
    assert metrics.scan_status is None


def test_the_run_stage_records_decide_when_present_including_the_preflight() -> None:
    stages = (
        StageRecord(name="preflight", status="ok", duration_seconds=4.2),
        StageRecord(name="probe", status="ok", duration_seconds=40.0),
        StageRecord(name="scan", status="failed", duration_seconds=12.5),
        StageRecord(name="authz", status="skipped"),
        StageRecord(name="report", status="not_run"),
    )

    seconds = build(stages=stages, report_seconds=1.0).stages_seconds

    assert (seconds.preflight, seconds.probe, seconds.scan) == (4.2, 40.0, 12.5)
    assert seconds.authz is None
    assert seconds.report is None  # `not_run` não vira zero nem o valor derivado


def test_the_nuclei_stage_time_comes_from_the_run_record_and_skipped_is_none() -> None:
    ran = (StageRecord(name="nuclei", status="ok", duration_seconds=33.3),)
    skipped = (StageRecord(name="nuclei", status="skipped"),)

    assert build(stages=ran).stages_seconds.nuclei == 33.3
    assert build(stages=skipped).stages_seconds.nuclei is None
    assert build().stages_seconds.nuclei is None


def test_window_is_the_run_window_or_the_manifest_start_and_the_last_finish() -> None:
    assert build(run_window=("a", "b")).started_at == "a"
    assert build(run_window=("a", "b")).finished_at == "b"
    derived = build()
    assert derived.started_at == "2026-11-13T05:15:30+00:00"
    assert derived.finished_at == "2026-11-13T05:20:00+00:00"


def test_without_scan_probe_or_authz_there_is_no_end_and_nothing_is_invented() -> None:
    metrics = build(probe=None, scan=None)

    assert metrics.finished_at is None
    assert metrics.operations == ()
    assert metrics.scan_status is None
    assert metrics.rules.totals == ()
    assert metrics.traffic.available is False
    assert metrics.disabled_rules == ()


# ---------------------------------------------------------------- operações e regras


def test_each_operation_reuses_the_duration_and_requests_of_scan_json() -> None:
    metrics = build()

    (operation_metric,) = metrics.operations
    assert operation_metric.operation_id == "listar"
    assert operation_metric.duration_seconds == 3.5
    assert operation_metric.requests == 120
    assert operation_metric.outcome == "completed"
    assert metrics.scan_status == "completed"


def test_rules_are_attached_per_operation_and_summed_for_the_run() -> None:
    second = scan_result([entry("listar", "GET", "/a", 1), entry("criar", "POST", "/b", 2)])
    second = second.model_copy(
        update={
            "entries": (
                second.entries[0],
                second.entries[1].model_copy(update={"scan_id": "1"}),
            )
        }
    )
    file = stats(
        OperationRules(operation_id="listar", scan_id="0", rules=(rule(1, 300), rule(2, 50))),
        OperationRules(operation_id="criar", scan_id="1", rules=(rule(1, 200),)),
    )

    metrics = build(scan=second, rule_stats=file)

    assert [len(op.rules) for op in metrics.operations] == [2, 1]
    assert metrics.rules.operations_measured == 2
    top = metrics.rules.totals[0]
    assert (top.plugin_id, top.time_ms, top.operations) == (1, 500, 2)


def test_a_failed_collection_marks_the_operation_unavailable_with_the_reason() -> None:
    file = stats(OperationRules(operation_id="listar", scan_id="0", unavailable_reason="ZAP fora"))

    metrics = build(rule_stats=file)

    (operation_metric,) = metrics.operations
    assert operation_metric.rules_available is False
    assert operation_metric.rules_unavailable_reason == "ZAP fora"
    assert operation_metric.rules == ()
    assert (metrics.rules.operations_measured, metrics.rules.operations_unavailable) == (0, 1)


def test_a_scan_from_before_the_measurement_says_so_instead_of_showing_zero_rules() -> None:
    metrics = build(rule_stats=None)

    (operation_metric,) = metrics.operations
    assert operation_metric.rules_available is False
    assert "rule-stats.json" in (operation_metric.rules_unavailable_reason or "")


def test_an_operation_whose_scan_never_started_is_unavailable_for_that_reason() -> None:
    base = scan_result([entry("listar", "GET", "/a", 1)])
    refused = base.model_copy(
        update={"entries": (base.entries[0].model_copy(update={"scan_id": None}),)}
    )

    (operation_metric,) = build(scan=refused, rule_stats=stats()).operations

    assert operation_metric.rules_available is False
    assert "não chegou a começar" in (operation_metric.rules_unavailable_reason or "")


# ---------------------------------------------------------------- tráfego e regras desligadas


def test_traffic_totals_are_copied_from_scan_json_and_gaps_are_measured_from_the_audit() -> None:
    traffic = TrafficSummary(
        enabled=True, allowed=3, denied=1, denied_by_reason={"path_not_allowed": 1}
    )
    rows = [row(1), row(2), row(20), row(21, "deny")]

    metrics = build(scan=scan(traffic=traffic), proxy_rows=rows)

    assert metrics.traffic.available is True
    assert (metrics.traffic.allowed, metrics.traffic.denied) == (3, 1)
    assert metrics.traffic.denied_by_reason == {"path_not_allowed": 1}
    gaps = metrics.traffic.gaps
    assert gaps is not None
    assert (gaps.count, gaps.total_seconds, gaps.longest_seconds) == (1, 18.0, 18.0)
    assert gaps.threshold_seconds == 10.0


def test_gaps_are_unknown_not_zero_without_the_audit_or_with_an_audit_from_another_stack() -> None:
    traffic = TrafficSummary(enabled=True, allowed=1)
    other_stack = [
        ProxyRow(at=SCAN_START - timedelta(days=3), decision="allow", reason="x", method="GET")
    ]

    assert build(scan=scan(traffic=traffic), proxy_rows=None).traffic.gaps is None
    assert build(scan=scan(traffic=traffic), proxy_rows=other_stack).traffic.gaps is None


def test_traffic_is_unavailable_when_the_scan_had_no_proxy_audit() -> None:
    assert build(proxy_rows=[row(1)]).traffic.available is False


def test_disabled_rules_carry_the_reason_and_the_source() -> None:
    base = scan()
    policy = base.policy.model_copy(update={"disabled_rules": (40044, 99999)})

    metrics = build(scan=base.model_copy(update={"policy": policy}))

    known, custom = metrics.disabled_rules
    assert (known.plugin_id, known.source) == (40044, "default")
    assert known.name is not None
    assert known.reason
    assert (custom.plugin_id, custom.source, custom.name) == (99999, "profile", None)


def test_the_file_has_only_numbers_and_identifiers_no_path_url_or_message() -> None:
    file = stats(OperationRules(operation_id="listar", scan_id="0", rules=(rule(1),)))

    text = build(rule_stats=file).model_dump_json()

    assert "/users/v1" not in text
    assert "http" not in text
    assert "message" not in text


def test_tempos_do_proxy_excluem_negados_e_preservam_dado_ausente() -> None:
    first = row(1).model_copy(update={"grant_wait_ms": 125, "network_ms": 250})
    denied = row(2, "deny").model_copy(update={"grant_wait_ms": 900, "network_ms": None})
    metrics = build(proxy_rows=[first, denied])
    assert metrics.timing.proxy_grant_wait_seconds == 0.125
    assert metrics.timing.proxy_network_seconds == 0.25
    assert metrics.timing.cpu_seconds is None
    old = row(3)
    mixed = build(proxy_rows=[first, old])
    assert mixed.timing.proxy_grant_wait_seconds is None
    assert mixed.timing.proxy_network_seconds is None
