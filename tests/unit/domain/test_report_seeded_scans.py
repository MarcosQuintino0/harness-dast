"""Relatório: operações varridas a partir de um resultado que não era sucesso (ADR 0050)."""

from harness_dast.domain.finding import Finding
from harness_dast.domain.report_build import assemble_report
from harness_dast.domain.report_html import render_html
from harness_dast.domain.report_labels import seeded_scans_notice
from harness_dast.domain.report_markdown import render_markdown
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.scan_plan import ScanSkip, SkipReason
from tests.fakes.zap_alerts import zap_alert
from tests.unit.domain.report_helpers import entry, operation, probe_result, scan_result

PATH = "/pacientes/{id}"


def build(
    *,
    seed: str | None,
    include: tuple[str, ...] = (),
    outcome: str = "not_found",
    status: int | None = 404,
    scanned: bool = True,
    skip_reason: SkipReason = "not_success",
    alerts: bool = True,
) -> FindingsReport:
    ops = [operation("buscar", "GET", PATH, outcome, status=status)]
    entries = [entry("buscar", "GET", PATH, 4, alert_ids=("9",), seed_outcome=seed)]
    skips = [
        ScanSkip(operation_id="buscar", method="GET", path=PATH, reason=skip_reason, message="x")
    ]
    return assemble_report(
        probe=probe_result(ops),
        scan=scan_result(
            entries if scanned else [],
            skipped=[] if scanned else skips,
            include_outcomes=include,
        ),
        raw_alerts=[zap_alert("9")] if alerts else [],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="t",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
    )


def test_coverage_lists_the_operation_scanned_from_a_not_found_seed() -> None:
    report = build(seed="not_found", include=("not_found",))

    (item,) = report.coverage.seeded_scans
    assert (item.operation_id, item.seed_outcome, item.probe_status) == ("buscar", "not_found", 404)
    assert report.coverage.include_outcomes == ("not_found",)
    assert report.coverage.not_tested == ()


def test_seed_does_not_count_as_reached_by_the_probe() -> None:
    report = build(seed="not_found", include=("not_found",))

    assert report.coverage.probe_successes == 0
    assert report.coverage.reachability == 0.0


def test_a_success_scan_has_no_seeded_scans() -> None:
    report = build(seed=None, outcome="success", status=200)

    assert report.coverage.seeded_scans == ()
    assert "semente" not in render_markdown(report)
    assert "semente" not in render_html(report)


def test_the_finding_carries_the_seed_and_the_fingerprint_ignores_it() -> None:
    seeded = build(seed="not_found", include=("not_found",))
    plain = build(seed=None, outcome="success", status=200)

    assert seeded.findings[0].seed_outcome == "not_found"
    assert plain.findings[0].seed_outcome is None
    assert seeded.findings[0].fingerprint == plain.findings[0].fingerprint
    assert seeded.groups[0].locations[0].seed_outcome == "not_found"


def test_markdown_and_html_say_the_fixed_notice_the_table_and_the_tag() -> None:
    report = build(seed="not_found", include=("not_found",))
    notice = seeded_scans_notice(1)

    for raw in (render_markdown(report), render_html(report)):
        text = raw.replace("\\", "")
        assert "1 operações foram varridas a partir de uma resposta que não foi sucesso" in text
        assert "não indica que a operação é segura" in text
        assert "semente: not_found" in text
    assert notice.startswith("1 operações")


def test_markdown_tags_the_finding_line_and_the_summary_row() -> None:
    text = render_markdown(build(seed="not_found", include=("not_found",))).replace("\\", "")

    assert text.count("(semente: not_found)") >= 3


def test_unscanned_404_asks_the_letter_when_the_class_is_not_in_the_applied_list() -> None:
    report = build(seed=None, scanned=False, alerts=False)

    (item,) = report.coverage.not_tested
    assert item.reason == "not_success"
    assert item.message.startswith("O probe observou HTTP 404. x")
    assert "Para varrê-la a carta precisa autorizar `scan.include_outcomes: not_found`" in (
        item.message
    )
    assert "HTTP 404" in render_markdown(report)


def test_unscanned_with_the_class_applied_keeps_its_own_reason_without_the_ask() -> None:
    report = build(
        seed=None, scanned=False, alerts=False, include=("not_found",), skip_reason="denied"
    )

    (item,) = report.coverage.not_tested
    assert item.reason == "denied"
    assert "include_outcomes" not in item.message


def test_a_class_outside_the_closed_list_never_suggests_the_letter() -> None:
    report = build(seed=None, scanned=False, alerts=False, outcome="auth_error", status=401)

    (item,) = report.coverage.not_tested
    assert "include_outcomes" not in item.message


def test_an_old_scan_without_the_new_fields_still_builds_the_report() -> None:
    report = build(seed=None, outcome="success", status=200)
    data = report.model_dump(mode="json")
    del data["coverage"]["seeded_scans"]
    del data["coverage"]["include_outcomes"]
    for found in data["findings"]:
        del found["seed_outcome"]

    again = FindingsReport.model_validate(data)

    assert again.coverage.seeded_scans == ()
    assert all(isinstance(item, Finding) and item.seed_outcome is None for item in again.findings)
