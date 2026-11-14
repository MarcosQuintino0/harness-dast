"""Agrupamento por causa: junta o que tem a mesma origem, não apaga nem muda nada."""

import pytest

from harness_dast.domain.finding import Finding
from harness_dast.domain.finding_group import group_findings
from harness_dast.domain.known_patterns import expected_pattern_note
from harness_dast.domain.report_build import assemble_report
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.scan_plan import LearnedRef
from tests.fakes.zap_alerts import zap_alert
from tests.unit.domain.report_helpers import entry, operation, probe_result, scan_result

LEARNED = [
    LearnedRef(operation_id="obter", message_id=4),
    LearnedRef(operation_id="listar", message_id=6),
    LearnedRef(operation_id="criar", message_id=13),
]
OPS = [
    operation("obter", "GET", "/users/v1/{username}"),
    operation("listar", "GET", "/users/v1"),
    operation("criar", "POST", "/books/v1"),
]


def build(alerts: list[dict[str, str]]) -> FindingsReport:
    entries = [
        entry("obter", "GET", "/users/v1/{username}", 4),
        entry("listar", "GET", "/users/v1", 6),
        entry("criar", "POST", "/books/v1", 13),
    ]
    return assemble_report(
        probe=probe_result(OPS),
        scan=scan_result(entries, learned=LEARNED),
        raw_alerts=alerts,
        evidence={},
        triage=None,
        baseline=None,
        generated_at="2026-11-13T06:00:00+00:00",
        harness_version="0.0-test",
        auth_header=None,
        csrf_header=None,
    )


def cookie(alert_id: str, source: str, name: str = "XSRF-TOKEN") -> dict[str, str]:
    return zap_alert(
        alert_id,
        pluginId="10010",
        alertRef="10010",
        alert="Cookie No HttpOnly Flag",
        cweid="1004",
        risk="Low",
        param=name,
        inputVector="",
        sourceMessageId=source,
    )


def sqli(alert_id: str, source: str, **changes: str) -> dict[str, str]:
    return zap_alert(alert_id, sourceMessageId=source, **changes)


def test_same_rule_parameter_and_severity_on_many_paths_become_one_group() -> None:
    report = build([cookie("1", "4"), cookie("2", "6"), cookie("3", "13")])

    (group,) = report.groups
    assert group.findings_count == 3
    assert group.occurrences == 3
    assert {loc.path_template for loc in group.locations} == {
        "/users/v1/{}",
        "/users/v1",
        "/books/v1",
    }
    assert group.finding_ids == tuple(item.finding_id for item in report.findings)


def test_three_sql_injection_alerts_with_the_same_cause_become_one_group() -> None:
    report = build([sqli("1", "4"), sqli("2", "6"), sqli("3", "13")])

    assert len(report.findings) == 3
    (group,) = report.groups
    assert group.title == "SQL Injection"
    assert group.proposed_severity == "high"
    assert group.findings_count == 3


def test_a_different_parameter_rule_or_severity_makes_a_different_group() -> None:
    report = build(
        [
            sqli("1", "4", param="id", inputVector="json"),
            sqli("2", "6", param="nome", inputVector="json"),
            sqli("3", "13", risk="Medium"),
            cookie("4", "4", name="outro"),
        ]
    )

    assert len(report.groups) == 4
    assert sum(group.findings_count for group in report.groups) == len(report.findings)


def test_every_finding_is_in_exactly_one_group_and_none_is_changed() -> None:
    report = build([cookie("1", "4"), cookie("2", "6"), sqli("3", "13")])

    in_groups = [fid for group in report.groups for fid in group.finding_ids]
    assert sorted(in_groups) == sorted(item.finding_id for item in report.findings)
    assert all(item.proposed_severity in {"low", "high"} for item in report.findings)
    assert all(item.status == "needs_triage" for item in report.findings)


def test_groups_are_ordered_by_severity_then_size_and_the_ids_are_stable() -> None:
    alerts = [cookie("1", "4"), cookie("2", "6"), sqli("3", "13")]

    first = build(alerts).groups
    second = build(list(reversed(alerts))).groups

    assert [g.proposed_severity for g in first] == ["high", "low"]
    assert [g.group_id for g in first] == [g.group_id for g in second]
    assert all(g.group_id.startswith("G-") and len(g.group_id) == 10 for g in first)


def test_no_findings_means_no_groups() -> None:
    assert group_findings(()) == ()
    assert build([]).groups == ()


def test_the_xsrf_cookie_group_carries_the_fixed_note_without_changing_severity() -> None:
    report = build([cookie("1", "4"), cookie("2", "6")])

    (group,) = report.groups
    assert group.expected_note is not None
    assert "duplo envio" in group.expected_note
    assert group.proposed_severity == "low"
    assert {item.proposed_severity for item in report.findings} == {"low"}


def test_a_session_cookie_gets_no_expected_note() -> None:
    report = build([cookie("1", "4", name="JSESSIONID")])

    assert report.groups[0].expected_note is None


@pytest.mark.parametrize("name", ["xsrf-token", "XSRF-TOKEN", " X-XSRF-TOKEN ", "csrf-token"])
def test_known_pattern_matches_csrf_cookie_names_in_any_case(name: str) -> None:
    assert expected_pattern_note("10010", name) is not None


@pytest.mark.parametrize(("plugin", "name"), [("10011", "XSRF-TOKEN"), ("10010", ""), ("", "x")])
def test_known_pattern_is_exact_about_rule_and_cookie(plugin: str, name: str) -> None:
    assert expected_pattern_note(plugin, name) is None


def test_findings_json_without_groups_still_loads_and_groups_round_trip() -> None:
    report = build([cookie("1", "4"), cookie("2", "6")])
    data = report.model_dump(mode="json")
    del data["groups"]

    assert FindingsReport.model_validate(data).groups == ()
    assert FindingsReport.model_validate(report.model_dump(mode="json")) == report


def test_group_of_findings_from_another_origin_uses_the_same_rule() -> None:
    base: Finding = build([sqli("1", "4")]).findings[0]
    other = base.model_copy(
        update={"finding_id": "F-00000001", "path_template": "/contas/{}", "occurrences": 2}
    )

    (group,) = group_findings((base, other))

    assert group.findings_count == 2
    assert group.occurrences == base.occurrences + 2
