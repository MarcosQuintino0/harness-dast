"""Dados sintéticos para testes de verificação."""

from harness_dast.domain.finding import Classification, Finding, FindingEvidence

RUN = "2026-11-16T12-00-00Z-produto-abcd"
FP = "a" * 64


def finding(*, proof: str = "trecho", available: bool = True, false: bool = False) -> Finding:
    return Finding(
        finding_id="F-aaaaaaaa",
        fingerprint=FP,
        title="alerta",
        plugin_id="1",
        alert_ref="1",
        classification=Classification(),
        proposed_severity="high",
        proposed_confidence="false_positive" if false else "high",
        method="GET",
        path_template="/x",
        attribution="scan",
        occurrences=1,
        evidence=FindingEvidence(zap_evidence=proof, available=available),
    )


def envelope() -> dict[str, object]:
    return {"schema_version": 1, "product": "produto", "run_id": RUN, "entries": []}
