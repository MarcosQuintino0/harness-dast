"""Textos de confiança correspondem à técnica e à política registradas."""

import pytest

from harness_dast.domain.panel.authz_copy import authz_confidence_text
from harness_dast.domain.panel.model import PanelFinding


@pytest.mark.parametrize(
    ("technique", "parameter", "expected"),
    [
        ("authz_cors", "reflected_credentials", "refletiu uma origem estranha"),
        ("authz_cors", "wildcard", "qualquer origem sem credenciais"),
        ("authz_cors", "[REDACTED]", "política CORS"),
        ("authz_excessive_data", "", "OpenAPI não declara"),
        ("authz_horizontal", "", "outra conta"),
        ("authz_vertical", "", "conta de papel menor e observou sucesso"),
        ("authz_horizontal_write", "", "outra conta"),
        ("authz_anonymous_access", "", "teste de autorização"),
        (None, "", "teste de autorização"),
    ],
)
def test_confidence_describes_observation_when_technique_varies(
    technique: str | None, parameter: str, expected: str
) -> None:
    item = PanelFinding.model_validate(
        dict(
            finding_id="A-1",
            origin="authz",
            title="achado",
            severity="high",
            confidence=2,
            method="GET",
            path_template="/",
            authz_technique=technique,
            parameter=parameter,
        )
    )

    assert expected in authz_confidence_text(item)
