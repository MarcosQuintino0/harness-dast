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
