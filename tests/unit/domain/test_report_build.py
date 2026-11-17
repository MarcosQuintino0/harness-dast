"""Relatório: cobertura honesta, triagem como coluna extra e comparação entre execuções."""

from collections.abc import Mapping, Sequence

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import FINGERPRINT_VERSION
from harness_dast.domain.report_build import assemble_report, build_resolver
from harness_dast.domain.report_html import render_html
from harness_dast.domain.report_markdown import render_markdown
from harness_dast.domain.report_model import NOT_TESTED_STATEMENTS, FindingsReport
from harness_dast.domain.scan_plan import LearnedRef, ScanSkip
from harness_dast.domain.triage import parse_triage
from tests.fakes.zap_alerts import zap_alert
from tests.unit.domain.report_helpers import (
    OTHER_RUN_ID,
    entry,
    operation,
    probe_result,
    scan_result,
)

OPS = [
    operation("obter", "GET", "/users/v1/{username}"),
    operation("login", "POST", "/users/v1/login"),
    operation(
        "remover",
        "DELETE",
        "/users/v1/{username}",
        "skipped_destructive",
        message="DELETE é pulado.",
    ),
    operation("falha", "POST", "/books/v1", "validation_error"),
]


def assemble(
    alerts: Sequence[Mapping[str, object]] | None = None,
    *,
    triage: object = None,
    baseline: FindingsReport | None = None,
    run_id: str | None = None,
) -> FindingsReport:
    probe = probe_result(OPS)
    scan = scan_result(
        [entry("obter", "GET", "/users/v1/{username}", 4, alert_ids=("9",))],
        learned=[LearnedRef(operation_id="obter", message_id=4)],
        skipped=[
            ScanSkip(
                operation_id="login",
                method="POST",
                path="/users/v1/login",
                reason="login",
                message="O login não é varrido.",
            )
        ],
    )
    return assemble_report(
        probe=probe,
        scan=scan,
        raw_alerts=[zap_alert("9")] if alerts is None else alerts,
        evidence={},
        triage=parse_triage(triage) if triage is not None else None,
        baseline=baseline,
        generated_at="2026-11-13T06:00:00+00:00",
        harness_version="0.0-test",
        auth_header=("Authorization", "Bearer $TOKEN"),
        csrf_header=None,
    )


def test_every_report_carries_the_fixed_not_tested_statements_even_without_findings() -> None:
    report = assemble([])

    assert report.not_tested_statements == NOT_TESTED_STATEMENTS
    assert report.findings == ()
    assert any("NÃO é evidência" in text for text in report.not_tested_statements)
    assert any("BOLA" in text for text in report.not_tested_statements)
    assert any("mass assignment" in text for text in report.not_tested_statements)


def test_coverage_lists_what_was_not_tested_and_why() -> None:
    report = assemble()

    reasons = {item.operation_id: item.reason for item in report.coverage.not_tested}
    assert reasons == {
        "login": "login",
        "remover": "probe_skipped_destructive",
        "falha": "probe_validation_error",
    }
    assert report.coverage.reachability == pytest.approx(2 / 3, abs=1e-3)
    assert report.coverage.limits.threads_per_host == 2
    assert report.coverage.policy.url_path_injection is True
    assert report.coverage.scans_run == 1


@pytest.mark.parametrize(("method", "path"), [("GET", "/catalog/{id}"), ("POST", "/orders")])
def test_completed_run_marks_unscanned_eligible_operation_partial(method: str, path: str) -> None:
    from harness_dast.domain.panel.build import build_panel_view
    from harness_dast.domain.panel.coverage import render_coverage
    from tests.unit.domain.panel.helpers import sources

    probe = probe_result(
        [operation("pending", method, path, "validation_error", message="Inválido")]
    )
    scan = scan_result([])
    report = assemble_report(
        probe=probe,
        scan=scan,
        raw_alerts=[],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="t",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
    )
    panel = render_coverage(build_panel_view(sources(probe=probe, scan=scan)))

    assert report.coverage.partial
    assert report.coverage.not_tested[0].probe_outcome == "validation_error"
    for text in (render_markdown(report), render_html(report), panel, report.model_dump_json()):
        assert "pending" in text
        assert path in text
        assert "validation_error" in text.replace("\\_", "_")
    assert "Cobertura parcial" in panel


def test_design_exclusion_alone_does_not_make_coverage_partial() -> None:
    from harness_dast.domain.report_build import coverage_gaps

    probe = probe_result([operation("remove", "DELETE", "/items/{id}", "skipped_destructive")])
    assert coverage_gaps(probe, scan_result([])) == ()


def test_scanned_unreached_operation_still_marks_coverage_partial() -> None:
    from harness_dast.domain.report_build import coverage_is_partial

    probe = probe_result([operation("find", "GET", "/items/{id}", "not_found")])
    scan = scan_result([entry("find", "GET", "/items/{id}", 1, seed_outcome="not_found")])
    assert coverage_is_partial(probe, scan)


@pytest.mark.parametrize(("method", "path"), [("GET", "/stock"), ("POST", "/sessions")])
def test_refused_scan_is_listed_as_unscanned(method: str, path: str) -> None:
    from harness_dast.domain.panel.build import build_panel_view
    from harness_dast.domain.panel.coverage import render_coverage
    from tests.unit.domain.panel.helpers import sources

    probe = probe_result([operation("pending", method, path)])
    refused = entry("pending", method, path, 1, outcome="refused").model_copy(
        update={"note": "O ZAP recusou iniciar a varredura: indisponível."}
    )
    scan = scan_result([refused])
    report = assemble_report(
        probe=probe,
        scan=scan,
        raw_alerts=[],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="t",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
    )
    panel = render_coverage(build_panel_view(sources(probe=probe, scan=scan)))

    assert report.coverage.partial
    assert report.coverage.scans_run == 0
    assert report.coverage.truncated_scans == ()
    (item,) = report.coverage.not_tested
    assert (item.operation_id, item.method, item.path, item.probe_outcome) == (
        "pending",
        method,
        path,
        "success",
    )
    assert item.reason == "scan_refused"
    for text in (render_markdown(report), render_html(report), panel):
        assert "pending" in text
        assert path in text
        assert "indisponível" in text


def test_refused_scan_without_note_explains_why_it_did_not_run() -> None:
    from harness_dast.domain.report_build import coverage_gaps

    probe = probe_result([operation("read", "GET", "/inventory")])
    scan = scan_result([entry("read", "GET", "/inventory", 1, outcome="refused")])
    (gap,) = coverage_gaps(probe, scan)
    assert gap.message == "O ZAP recusou iniciar a varredura."


def test_old_not_success_skip_for_expected_login_is_a_design_exclusion() -> None:
    from harness_dast.domain.report_build import coverage_gaps, coverage_is_partial

    item = operation("sign_in", "POST", "/sessions").model_copy(
        update={"outcome": "auth_rejected_expected", "status": 401}
    )
    probe = probe_result([item])
    scan = scan_result(
        [],
        skipped=[
            ScanSkip(
                operation_id="sign_in",
                method="POST",
                path="/sessions",
                reason="not_success",
                message="O probe não teve sucesso.",
            )
        ],
    )
    assert coverage_gaps(probe, scan) == ()
    assert not coverage_is_partial(probe, scan)


@pytest.mark.parametrize("path", ["/sessions", "/access/token"])
def test_expected_login_rejection_is_reached_and_excluded_from_scanning(path: str) -> None:
    from harness_dast.domain.panel.build import build_panel_view
    from harness_dast.domain.panel.coverage import render_coverage
    from tests.unit.domain.panel.helpers import sources

    # Aceita o contrato novo também enquanto o módulo de probe é integrado em outra branch.
    item = operation("sign_in", "POST", path).model_copy(
        update={"outcome": "auth_rejected_expected", "status": 401}
    )
    probe = probe_result([item])
    scan = scan_result(
        [],
        skipped=[
            ScanSkip(
                operation_id="sign_in",
                method="POST",
                path=path,
                reason="login",
                message="O login não é varrido.",
            )
        ],
    )
    report = assemble_report(
        probe=probe,
        scan=scan,
        raw_alerts=[],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="t",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
    )
    panel = render_coverage(build_panel_view(sources(probe=probe, scan=scan)))

    assert report.coverage.probe_reached == 1
    assert report.coverage.probe_successes == 0
    assert not report.coverage.partial
    stages = build_panel_view(sources(probe=probe, scan=scan)).stages
    probe_stage = next(stage for stage in stages if stage.key == "probe")
    assert "0 com sucesso e 1 com recusa esperada de login" in probe_stage.summary
    for text in (render_markdown(report), render_html(report), panel):
        assert "Recusa esperada" in text
        assert "login não é varrido" in text


def test_truncated_scans_are_listed_in_the_coverage() -> None:
    probe = probe_result(OPS[:1])
    scan = scan_result([entry("obter", "GET", "/users/v1/{username}", 4, outcome="truncated")])

    report = assemble_report(
        probe=probe,
        scan=scan,
        raw_alerts=[],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="t",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
    )

    assert [(t.operation_id, t.outcome, t.progress) for t in report.coverage.truncated_scans] == [
        ("obter", "truncated", 45)
    ]


def test_malformed_alerts_are_counted_and_skipped_not_fatal() -> None:
    report = assemble([zap_alert("9"), {"id": ["nao", "texto"], "risk": {"x": 1}}])

    assert report.summary.alerts_unreadable == 1
    assert report.summary.total == 1


def test_summary_counts_by_proposed_severity() -> None:
    alerts = [
        zap_alert("9"),
        zap_alert("10", pluginId="1", alertRef="1", risk="Low"),
        zap_alert("11", pluginId="2", alertRef="2", risk="Weird"),
    ]

    report = assemble(alerts)

    assert report.summary.by_severity == {
        "high": 1,
        "medium": 0,
        "low": 1,
        "informational": 0,
        "unknown": 1,
    }
    assert report.summary.occurrences == 3


def test_resolver_links_learned_messages_and_scan_alerts_to_probe_operations() -> None:
    probe = probe_result(OPS)
    scan = scan_result(
        [entry("obter", "GET", "/users/v1/{username}", 4, alert_ids=("9",))],
        learned=[
            LearnedRef(operation_id="obter", message_id=4),
            LearnedRef(operation_id="x", message_id=5),
        ],
    )

    resolver = build_resolver(probe, scan)

    assert resolver.by_message[4].operation_id == "obter"
    assert 5 not in resolver.by_message
    assert resolver.by_alert["9"].operation_id == "obter"


def test_triage_is_a_separate_column_that_cannot_delete_or_rerate() -> None:
    plain = assemble()
    annotated = assemble(
        triage={
            "schema_version": 1,
            "annotations": [
                {
                    "fingerprint": plain.findings[0].fingerprint,
                    "suspected_false_positive": True,
                    "reason": "resposta 500 sem SQL",
                },
                {"fingerprint": "f" * 64, "note": "órfã"},
            ],
        }
    )

    assert len(annotated.findings) == len(plain.findings)
    assert annotated.findings[0].proposed_severity == plain.findings[0].proposed_severity
    assert annotated.findings[0].triage is not None
    assert annotated.triage_orphans == ("f" * 64,)
    assert annotated.summary == plain.summary


def test_compare_marks_new_persistent_and_not_observed_by_fingerprint() -> None:
    old = assemble(
        [
            zap_alert("9"),
            zap_alert("10", pluginId="40012", alertRef="40012", alert="XSS", cweid="79"),
        ]
    ).model_copy(update={"run_id": OTHER_RUN_ID})

    report = assemble(
        [zap_alert("9"), zap_alert("11", pluginId="1", alertRef="1", alert="Novo", risk="Low")],
        baseline=old,
    )

    marks = {f.title: f.comparison for f in report.findings}
    assert marks == {"SQL Injection": "persistent", "Novo": "new"}
    assert [g.title for g in report.not_observed] == ["XSS"]
    assert report.comparison is not None
    assert (
        report.comparison.new,
        report.comparison.persistent,
        report.comparison.not_observed,
    ) == (1, 1, 1)
    assert "não significa 'corrigido'" in report.comparison.notice
    assert assemble().comparison is None


def test_not_observed_says_whether_the_operation_was_scanned_now() -> None:
    old = assemble([zap_alert("9")]).model_copy(update={"run_id": OTHER_RUN_ID})
    gone_elsewhere = old.findings[0].model_copy(
        update={"operation_id": "outra", "fingerprint": "e" * 64}
    )
    old = old.model_copy(update={"findings": (*old.findings, gone_elsewhere)})

    report = assemble([zap_alert("9")], baseline=old)

    (gone,) = report.not_observed
    assert gone.operation_scanned_now is False


def test_comparison_refuses_another_product_or_fingerprint_version() -> None:
    old = assemble().model_copy(update={"run_id": OTHER_RUN_ID})

    with pytest.raises(ConfigError, match="outro produto"):
        assemble(baseline=old.model_copy(update={"product": "outro"}))
    with pytest.raises(ConfigError, match="versão"):
        assemble(baseline=old.model_copy(update={"fingerprint_version": FINGERPRINT_VERSION + 1}))


def test_404_observado_preserva_motivo_do_scan_nos_tres_formatos() -> None:
    probe = probe_result([operation("ausente", "GET", "/x", "not_found", status=404)])
    skip = ScanSkip(
        operation_id="ausente",
        method="GET",
        path="/x",
        reason="not_success",
        message="O probe não teve sucesso.",
    )
    report = assemble_report(
        probe=probe,
        scan=scan_result([], skipped=[skip]),
        raw_alerts=[],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="t",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
    )

    (item,) = report.coverage.not_tested
    assert item.reason == "not_success"
    assert item.message.startswith("O probe observou HTTP 404. O probe não teve sucesso.")
    assert "scan.include_outcomes: not_found" in item.message
    assert "HTTP 404" in report.model_dump_json()
    assert "HTTP 404" in render_markdown(report)
    assert "HTTP 404" in render_html(report)


def test_404_sem_pulo_registrado_nao_inventa_motivo() -> None:
    probe = probe_result([operation("ausente", "GET", "/x", "not_found", status=404)])
    report = assemble_report(
        probe=probe,
        scan=scan_result([]),
        raw_alerts=[],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="t",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
    )

    (item,) = report.coverage.not_tested
    assert item.reason == "scan_sem_registro"
    assert item.message == (
        "O probe observou HTTP 404. Não há motivo de ausência de varredura registrado no scan."
    )


@pytest.mark.parametrize("status", [410, None])
def test_status_nao_404_preserva_tratamento_anterior(status: int | None) -> None:
    probe = probe_result([operation("ausente", "GET", "/x", "not_found", status=status)])
    report = assemble_report(
        probe=probe,
        scan=scan_result([]),
        raw_alerts=[],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="t",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
    )

    (item,) = report.coverage.not_tested
    assert item.reason == "probe_not_found"
    assert item.message == "O probe terminou com not_found."


def test_404_com_entrada_no_scan_nao_e_listado_como_sem_varredura() -> None:
    probe = probe_result([operation("ausente", "GET", "/x", "not_found", status=404)])
    report = assemble_report(
        probe=probe,
        scan=scan_result([entry("ausente", "GET", "/x", 1)]),
        raw_alerts=[],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="t",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
    )

    assert report.coverage.not_tested == ()
