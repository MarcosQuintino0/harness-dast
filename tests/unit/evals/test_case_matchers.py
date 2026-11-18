"""Toda falha detectável de todo caso precisa de critério de reconhecimento na régua."""

import pytest

from evals.runner.cases import CASES_DIR, load_case
from evals.runner.checks_findings import flaw_status

CASE_NAMES = sorted(item.name for item in CASES_DIR.iterdir() if (item / "case.yml").is_file())


@pytest.mark.parametrize("name", CASE_NAMES)
def test_falha_detectavel_tem_criterio_quando_caso_e_carregado(name: str) -> None:
    case = load_case(name)
    sem_criterio = [
        flaw.id for flaw in case.flaws if flaw.detectable and not (flaw.match or flaw.match_any)
    ]
    assert sem_criterio == []


def test_crapi_foco_reconhece_token_adulterado_quando_authz_o_acusa() -> None:
    case = load_case("crapi-foco")
    jwt = next(flaw for flaw in case.flaws if flaw.id == "C15")
    achado = {
        "technique": "authz_tampered_token",
        "title": "GET /identity/api/v2/vehicle/vehicles aceita um token adulterado",
        "method": "GET",
        "path_template": "/identity/api/v2/vehicle/vehicles",
    }
    assert flaw_status(jwt, [achado]) == "achada"


def test_crapi_foco_reconhece_ssrf_guiado_quando_retorno_e_observado() -> None:
    case = load_case("crapi-foco")
    ssrf = next(flaw for flaw in case.flaws if flaw.id == "C11")
    achado = {
        "title": "Server-Side Request Forgery (retorno fora de banda observado)",
        "operation_id": "contact_mechanic",
        "method": "POST",
        "path_template": "/workshop/api/merchant/contact_mechanic",
    }
    assert flaw_status(ssrf, [achado]) == "achada"
