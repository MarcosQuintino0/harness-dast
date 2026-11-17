"""Contrato do cadastro local do crAPI sem rede real."""

import httpx
import pytest

from harness_dast.adapters.docker.crapi_accounts import CrapiAccountProvisioner
from harness_dast.application.stack_models import LabAccountPaths
from harness_dast.domain.errors import ExternalToolError

CREDENTIALS = {
    "CRAPI_USER_A_EMAIL": "a@example.com",
    "CRAPI_USER_A_PASSWORD": "Aa1#secret-a",
    "CRAPI_USER_B_EMAIL": "b@example.com",
    "CRAPI_USER_B_PASSWORD": "Aa1#secret-b",
}
PATHS = LabAccountPaths(
    signup="/test/register", login="/test/login", resend="/test/resend", vehicle="/test/vehicle"
)


def test_cadastra_duas_contas_e_veiculos_por_loopback() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "Raw": {
                                "To": [f"{letter}@example.com"],
                                "Data": "VIN: 4ILKA33BRDC125835 Pincode: 4219",
                            }
                        }
                        for letter in ("a", "b")
                    ]
                },
            )
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"token": "abc"})
        return httpx.Response(200, json={})

    CrapiAccountProvisioner(httpx.MockTransport(handle), lambda _: None).provision(
        CREDENTIALS, PATHS
    )

    assert len(requests) == 10
    assert all(request.url.host == "127.0.0.1" for request in requests)
    assert sum(request.url.path == PATHS.vehicle for request in requests) == 2
    assert {request.url.path for request in requests if request.method == "POST"} == {
        PATHS.signup,
        PATHS.login,
        PATHS.resend,
        PATHS.vehicle,
    }


def test_erro_do_alvo_nao_divulga_corpo_nem_credenciais() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=CREDENTIALS["CRAPI_USER_A_PASSWORD"])

    with pytest.raises(ExternalToolError) as error:
        CrapiAccountProvisioner(httpx.MockTransport(handle), lambda _: None).provision(
            CREDENTIALS, PATHS
        )

    assert CREDENTIALS["CRAPI_USER_A_PASSWORD"] not in str(error.value)


@pytest.mark.parametrize("body", [{}, {"token": None}, "inválido"])
def test_login_invalido_ou_ausente_vira_erro_sem_expor_resposta(body: object) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json=body)
        return httpx.Response(200, json={})

    with pytest.raises(ExternalToolError, match="cadastrar"):
        CrapiAccountProvisioner(httpx.MockTransport(handle), lambda _: None).provision(
            CREDENTIALS, PATHS
        )
