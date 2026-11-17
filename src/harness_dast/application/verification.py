"""Caso de uso de verificação offline: não envia pedidos nem altera achados."""

from collections.abc import Sequence

from harness_dast.domain.finding import Finding
from harness_dast.domain.verification import VerificationFile, classify_finding, parse_verification


def verify_offline(product: str, run_id: str, findings: Sequence[Finding]) -> VerificationFile:
    """Monta envelope validado com uma classificação para cada achado.

    Raises:
        ConfigError: Se a identidade ou os fingerprints forem inválidos ou repetidos.
    """
    return parse_verification(
        {
            "schema_version": 1,
            "product": product,
            "run_id": run_id,
            "entries": [classify_finding(finding) for finding in findings],
        }
    )
