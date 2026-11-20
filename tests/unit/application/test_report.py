"""Caso de uso `report`: sem rede, gate de severidade, triagem e comparação, de ponta a ponta."""

from typing import Any

import pytest

from harness_dast.application.report import ReportRequest, exceeds
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.rule_stats import RuleStat
from tests.fakes.rig import PASSWORD, TOKEN, agenda_flows, agenda_profile
from tests.fakes.scan_rig import ScanRig
from tests.fakes.zap_alerts import attack_message, zap_alert

OTHER = "2026-11-09T10-00-00Z-agenda-beef"


def scanned(profile: Any = None, *, risk: str = "High", completed_rules: bool = False) -> ScanRig:
    rig = ScanRig(flows=agenda_flows(), profile=profile)
    if completed_rules:
        rig.zap.rule_stats = (RuleStat(plugin_id=1, name="x", state="completed"),)
    rig.run_probe()
    rig.zap.messages[1604] = attack_message(1604, token=TOKEN, body=f'{{"password": "{PASSWORD}"}}')

    def alerts(request: Any, zap: Any) -> list[dict[str, str]]:
        if request.method != "GET" or "/pacientes/" not in request.url:
            return []
        learned = next(
            m for m in zap.messages.values() if m.type == "1" and "/pacientes/" in m.request_header
        )
        return [
            zap_alert(
                risk=risk,
                sourceMessageId=str(learned.id),
                url="https://api.hml.acme-teste.net.br/api/pacientes/'",
                evidence=f"Authorization: Bearer {TOKEN}",
            )
        ]

    rig.zap.alert_factory = alerts
    rig.run_scan()
    return rig


def request(rig: ScanRig, **changes: Any) -> ReportRequest:
    return ReportRequest(product="agenda", run_id=rig.probe_result.run_id, **changes)


def test_report_turns_alerts_into_findings_resolved_by_the_learned_request() -> None:
    rig = scanned()

    outcome = rig.report().execute(request(rig))

    (finding,) = outcome.report.findings
    assert finding.operation_id == "buscar"
    assert finding.path_template == "/api/pacientes/{}"
    assert finding.attribution == "source_message"
    assert finding.evidence.available is True
    assert finding.reproduce_curl is not None
    assert "$TOKEN" in finding.reproduce_curl
    assert outcome.files == ("list.json",)


def test_report_never_touches_the_network_or_the_zap() -> None:
    rig = scanned()
    sent, calls = len(rig.target.requests), list(rig.zap.calls)

    rig.report().execute(request(rig))

    assert len(rig.target.requests) == sent
    assert rig.zap.calls == calls


def test_nothing_secret_reaches_the_report_or_its_serialisation() -> None:
    rig = scanned()

    outcome = rig.report().execute(request(rig))

    text = outcome.report.model_dump_json()
    assert TOKEN not in text
    assert PASSWORD not in text


def test_severity_gate_counts_findings_at_or_above_the_threshold() -> None:
    rig = scanned(risk="Medium")

    below = rig.report().execute(request(rig, fail_on="high"))
    at = rig.report().execute(request(rig, fail_on="medium"))
    low = rig.report().execute(request(rig, fail_on="low"))
    off = rig.report().execute(request(rig, fail_on="none"))

    assert [o.exceeds_threshold for o in (below, at, low, off)] == [False, True, True, False]


def test_threshold_comes_from_the_profile_and_the_flag_can_only_tighten_it() -> None:
    rig = scanned(agenda_profile(scan={"fail_on": "high"}))

    from_profile = rig.report().execute(request(rig))
    relaxed = rig.report().execute(request(rig, fail_on="none"))
    tightened = rig.report().execute(request(rig, fail_on="low"))

    assert (from_profile.threshold, from_profile.exceeds_threshold) == ("high", True)
    # `--fail-on none` não afrouxa o perfil (flags só reduzem).
    assert (relaxed.threshold, relaxed.exceeds_threshold) == ("high", True)
    assert tightened.threshold == "low"


def test_default_has_no_gate_so_findings_alone_never_change_the_exit_code() -> None:
    rig = scanned()

    outcome = rig.report().execute(request(rig))

    assert outcome.threshold == "none"
    assert outcome.exceeds_threshold is False


def test_triage_annotations_never_change_the_gate() -> None:
    rig = scanned()
    first = rig.report().execute(request(rig, fail_on="high"))
    rig.artifacts.triage[rig.probe_result.run_id] = {
        "schema_version": 1,
        "annotations": [
            {
                "fingerprint": first.report.findings[0].fingerprint,
                "suspected_false_positive": True,
                "reason": "parece falso positivo",
            }
        ],
    }

    second = rig.report().execute(request(rig, fail_on="high"))

    assert second.report.findings[0].triage is not None
    assert second.exceeds_threshold is True
    assert len(second.report.findings) == len(first.report.findings)


def test_invalid_triage_stops_the_report_with_a_config_error() -> None:
    rig = scanned()
    rig.artifacts.triage[rig.probe_result.run_id] = {"schema_version": 1, "annotations": [{"x": 1}]}

    with pytest.raises(ConfigError, match=r"triage\.json"):
        rig.report().execute(request(rig))


def test_compare_marks_findings_against_another_runs_findings() -> None:
    rig = scanned()
    baseline = rig.report().execute(request(rig)).report.model_copy(update={"run_id": OTHER})
    rig.artifacts.findings[OTHER] = baseline.model_copy(update={"findings": ()})

    outcome = rig.report().execute(request(rig, compare=OTHER))

    assert outcome.report.findings[0].comparison == "new"
    assert outcome.report.comparison is not None
    assert outcome.report.comparison.baseline_run_id == OTHER


def test_compare_with_the_same_run_or_a_missing_run_is_refused() -> None:
    rig = scanned()

    with pytest.raises(ConfigError, match="OUTRA"):
        rig.report().execute(request(rig, compare=rig.probe_result.run_id))
    with pytest.raises(ConfigError, match=r"findings\.json"):
        rig.report().execute(request(rig, compare=OTHER))
    with pytest.raises(ConfigError, match="inválido"):
        rig.report().execute(request(rig, compare="../x"))


def test_report_without_a_scan_or_for_another_product_is_a_config_error() -> None:
    rig = ScanRig(flows=agenda_flows())
    rig.run_probe()

    with pytest.raises(ConfigError, match=r"scan\.json"):
        rig.report().execute(request(rig))

    done = scanned()
    done.artifacts.scans[done.probe_result.run_id] = done.artifacts.scans[
        done.probe_result.run_id
    ].model_copy(update={"product": "outro"})
    with pytest.raises(ConfigError, match="outro produto"):
        done.report().execute(request(done))


def test_exceeds_helper_treats_none_as_off_and_unknown_severity_as_above_any_threshold() -> None:
    rig = scanned(risk="Weird")
    report = rig.report().execute(request(rig)).report

    assert report.findings[0].proposed_severity == "unknown"
    assert exceeds(report, "none") is False
    assert exceeds(report, "low") is True  # não soube classificar: o gate falha fechado
    assert exceeds(report, "high") is True


def test_report_marks_the_coverage_as_partial_when_the_scan_stopped_before_the_end() -> None:
    rig = scanned()
    run_id = rig.probe_result.run_id
    stopped = rig.artifacts.scans[run_id].model_copy(
        update={"status": "stopped_deadline", "stop_message": "O prazo acabou."}
    )
    rig.artifacts.scans[run_id] = stopped

    outcome = rig.report().execute(request(rig))

    assert outcome.report.coverage.partial is True
    assert outcome.report.coverage.scan_status == "stopped_deadline"


def test_report_is_not_partial_when_probe_and_scan_completed() -> None:
    rig = scanned(completed_rules=True)

    assert rig.report().execute(request(rig)).report.coverage.partial is False
