"""Reprodução manual de achados de autorização com evidência redigida."""

import pytest

from harness_dast.domain.authz.result import AuthzFinding, AuthzResult
from harness_dast.domain.panel.repro import render_repro
from tests.unit.domain.panel.helpers import view


def _authz(
    technique: str, fields: tuple[str, ...] = (), evidence: str = "observação"
) -> AuthzResult:
    finding = AuthzFinding.model_validate(
        dict(
            finding_id="A-1",
            fingerprint="f",
            technique=technique,
            title="achado",
            proposed_severity="high",
            cwe=942,
            owasp_api_2023="API8",
            operation_id="obter",
            method="GET",
            path_template="/x",
            actor_account="user_a",
            observed_status=200,
            fields=fields,
            evidence=evidence,
            description="",
            solution="",
        )
    )
    return AuthzResult(
        run_id="run",
        product="produto",
        status="completed",
        started_at="início",
        finished_at="fim",
        findings=(finding,),
    )


@pytest.mark.parametrize(
    ("technique", "fields", "expected"),
    [
        ("authz_cors", ("reflected_credentials",), "cabeçalho Origin enviado"),
        ("authz_excessive_data", (), "campos da resposta com o esquema do OpenAPI"),
        ("authz_vertical", (), "conta de papel menor e registrou o status de sucesso"),
        ("authz_horizontal", (), "comparação entre duas contas"),
    ],
)
def test_repro_descreve_tecnica_quando_achado_vem_de_authz(
    technique: str, fields: tuple[str, ...], expected: str
) -> None:
    panel = view(authz=_authz(technique, fields))
    item = next(item for item in panel.severe if item.origin == "authz")

    html = render_repro(item, panel)

    assert expected in html
    assert item.authz_technique == technique
    if technique != "authz_horizontal":
        assert "comparação entre duas contas" not in html
        assert "curl -i" not in html


@pytest.mark.parametrize("evidence", ["", "[REDACTED]", '<script>alert("x")</script>'])
def test_repro_escapa_evidencia_quando_recebe_texto_externo(evidence: str) -> None:
    panel = view(authz=_authz("authz_cors", ("reflected_credentials",), evidence))
    item = next(item for item in panel.severe if item.origin == "authz")

    html = render_repro(item, panel)

    assert "<script>" not in html
    assert "curl -i" not in html
    assert "não há passo a passo" in html
