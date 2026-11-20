"""Prova em memória de dois contratos, sem rede nem dados do laboratório."""

import pytest

from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.profile import ProductProfile
from tests.fakes.probe_ports import reply
from tests.fakes.rig import Rig, operation, profile_data


@pytest.mark.parametrize("login_path", ["/api/session", "/api/access"])
def test_so_a_operacao_do_login_recebe_recusa_esperada(login_path: str) -> None:
    data = profile_data()
    data["auth"]["token_path"] = login_path
    spec = ApiSpec(
        title="T",
        version="1",
        operations=(
            operation("session", "post", login_path, body={}),
            operation("other_method", "get", login_path),
            operation("protected", "get", "/api/private"),
        ),
    )

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": "test-token"})
        return reply(401, {"message": "denied"})

    result = (
        Rig(profile=ProductProfile.from_data(data), spec=spec, handler=handler)
        .probe()
        .execute(ProbeRequest(product="agenda"))
    )
    outcomes = {item.operation_id: item.outcome for item in result.operations}
    assert outcomes == {
        "session": "auth_rejected_expected",
        "other_method": "auth_error",
        "protected": "auth_error",
    }
    assert (result.summary.reached, result.summary.successes) == (1, 0)
