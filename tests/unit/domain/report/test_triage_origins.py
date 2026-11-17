"""Triagem reconhece fingerprints existentes em todas as origens do relatório."""

import pytest

from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.cors import cors_finding
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.report.build import assemble_report
from harness_dast.domain.signal_result import ProxySignals, SignalFinding
from harness_dast.domain.triage import parse_triage
from tests.unit.domain.negative_samples import accepted, negative_result
from tests.unit.domain.report.helpers import probe_result, scan_result


@pytest.mark.parametrize("origin", ["authz", "proxy_signals", "negative"])
def test_anotacao_de_achado_existente_nao_e_orfa_em_qualquer_origem(origin: str) -> None:
    exchange = ExchangeRecord(
        operation_id="readRecord",
        method="GET",
        path="/records/{id}",
        target="/records/1",
        account="a",
        status=200,
    )
    authz = AuthzResult(
        product="example",
        run_id="run",
        status="completed",
        started_at="a",
        finished_at="b",
        findings=(cors_finding("example", exchange, "member", 200, "reflected_credentials"),),
    )
    signals = ProxySignals(
        enabled=True,
        findings=(
            SignalFinding(
                finding_id="S-12345678",
                fingerprint="a" * 64,
                category="sql_error",
                title="Erro interno",
                proposed_severity="high",
                proposed_confidence="high",
                cwe=209,
                method="GET",
                path_template="/records/{id}",
                occurrences=1,
            ),
        ),
    )
    negative = negative_result(product="example", findings=(accepted(severity="high"),))
    sources: dict[str, AuthzResult | ProxySignals | NegativeResult] = {
        "authz": authz,
        "proxy_signals": signals,
        "negative": negative,
    }
    selected = sources[origin]
    fingerprint = selected.findings[0].fingerprint
    orphan = "f" * 64
    annotations = [
        {"fingerprint": item, "note": "Conferido; requer decisão humana."}
        for item in (fingerprint, orphan)
    ]

    report = assemble_report(
        probe=probe_result([]),
        scan=scan_result([]),
        raw_alerts=[],
        evidence={},
        triage=parse_triage({"schema_version": 1, "annotations": annotations}),
        baseline=None,
        generated_at="a",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
        authz=authz if origin == "authz" else None,
        proxy_signals=signals if origin == "proxy_signals" else None,
        negative=negative if origin == "negative" else None,
    )

    assert report.triage_orphans == (orphan,)
    assert selected.findings[0].proposed_severity == "high"
