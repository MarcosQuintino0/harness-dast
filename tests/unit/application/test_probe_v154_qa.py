"""Confere diagnóstico de conflito passando pelo caso de uso real."""

import pytest

from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.probe_ports import reply
from tests.fakes.rig import Rig, operation


@pytest.mark.parametrize(("route", "field"), [("/api/widgets", "serial"), ("/api/users", "handle")])
def test_fallback_do_conflito_aponta_campo_do_contrato(route: str, field: str) -> None:
    spec = ApiSpec(
        title="T",
        version="1",
        operations=(
            operation(
                "add",
                "post",
                route,
                body={field: Schema(type="string", max_length=16)},
                required=(field,),
            ),
        ),
    )

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": "token-sintetico-para-teste"})
        return reply(409, {"message": "valor duplicado"})

    result = Rig(spec=spec, handler=handler).probe().execute(ProbeRequest(product="agenda"))
    assert result.operations[0].conflict_fields == (field,)
