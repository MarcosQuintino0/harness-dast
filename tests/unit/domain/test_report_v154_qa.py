"""Revisão independente de cobertura de varredura recusada."""

from harness_dast.domain.report_build import assemble_report
from tests.unit.domain.report_helpers import entry, operation, probe_result, scan_result


def test_varredura_recusada_aparece_como_operacao_nao_varrida() -> None:
    probe = probe_result([operation("consulta", "GET", "/stock")])
    scan = scan_result([entry("consulta", "GET", "/stock", 1, outcome="refused")])
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
    assert report.coverage.partial is True
    assert [item.operation_id for item in report.coverage.not_tested] == ["consulta"]


def test_recusa_esperada_de_login_nao_torna_cobertura_integral_parcial() -> None:
    from harness_dast.domain.scan_plan import ScanSkip

    probe = probe_result([operation("session", "POST", "/session", "auth_rejected_expected")])
    skip = ScanSkip(
        operation_id="session",
        method="POST",
        path="/session",
        reason="not_success",
        message="O probe não teve sucesso nesta operação; não há requisição válida.",
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
    assert report.coverage.partial is False


def test_relatorios_escapam_texto_hostil_da_lacuna() -> None:
    from harness_dast.domain.report_html import render_html
    from harness_dast.domain.report_markdown import render_markdown
    from harness_dast.domain.scan_plan import ScanSkip

    probe = probe_result([operation("read", "GET", "/widgets", "auth_error")])
    skip = ScanSkip(
        operation_id="read",
        method="GET",
        path="/widgets",
        reason="not_success",
        message="<script>alert(1)</script> | injecao",
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
    assert "<script>alert(1)</script>" not in render_html(report)
    assert r"\<script\>" in render_markdown(report)
    assert r"\| injecao" in render_markdown(report)
