"""Contrato de classificação de login e diagnóstico de conflitos."""

import pytest

from harness_dast.domain.api_model import MediaBody, Operation, RequestBody
from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.http_messages import HttpResponse
from harness_dast.domain.outcome import classify_response
from harness_dast.domain.probe_conflict import annotate_blocked, conflict_fields
from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.probe_result import OperationResult, summarize_results


@pytest.mark.parametrize("status", [401, 403])
def test_login_rejeitado_conta_alcance_sem_ser_sucesso(status: int) -> None:
    response = HttpResponse(status=status, body=b'{"message":"denied"}')
    actual = classify_response(response, method="POST", success_rule=None, csrf=None, is_login=True)
    assert actual == "auth_rejected_expected"
    assert classify_response(response, method="POST", success_rule=None, csrf=None) == "auth_error"
    result = OperationResult(operation_id="login", method="POST", path="/session", outcome=actual)
    summary = summarize_results([result], 1)
    assert (summary.successes, summary.reached, summary.reachability) == (0, 1, 1.0)


def test_csrf_nao_vira_recusa_de_login() -> None:
    response = HttpResponse(status=403, body=b'{"message":"CSRF error"}')
    assert (
        classify_response(
            response,
            method="POST",
            success_rule=None,
            csrf=CsrfConfig(fetch_path="/csrf"),
            is_login=True,
        )
        == "csrf_error"
    )


@pytest.mark.parametrize(("field", "path"), [("serial", "/widgets"), ("handle", "/accounts")])
def test_conflito_usa_campo_do_alvo_ou_esquema(field: str, path: str) -> None:
    schema = Schema(
        type="object", required=(field,), properties={field: Schema(type="string", max_length=30)}
    )
    op = Operation(
        operation_id="create",
        method="post",
        path=path,
        request_body=RequestBody(
            media=(MediaBody(media_type="application/json", body_schema=schema),)
        ),
    )
    body: JsonValue = {field: "valor-nao-exibido"}
    origins = {f"body.{field}": False}
    reported = HttpResponse(
        status=409,
        body=(f'{{"errors":[{{"field":"{field}","message":"valor-nao-exibido"}}]}}').encode(),
    )
    assert conflict_fields(reported, op, body, origins) == (field,)
    assert conflict_fields(HttpResponse(status=409), op, body, origins) == (field,)
    assert conflict_fields(HttpResponse(status=409), op, body, {f"body.{field}": True}) == ()
    assert (
        conflict_fields(
            HttpResponse(status=409, body=b'{"errors":[{"field":"valor-nao-exibido"}]}'),
            op,
            body,
            {},
        )
        == ()
    )


def test_dependencias_transitivas_contadas_uma_vez() -> None:
    plan = tuple(
        PlannedOperation(
            operation_id=name, method="POST", path=f"/{name}", decision="send", depends_on=deps
        )
        for name, deps in [("a", ()), ("b", ("a",)), ("c", ("a", "b")), ("d", ())]
    )
    results = tuple(
        OperationResult.model_validate(
            {"operation_id": name, "method": "POST", "path": f"/{name}", "outcome": outcome}
        )
        for name, outcome in [
            ("a", "conflict"),
            ("b", "skipped_dependency"),
            ("c", "skipped_dependency"),
            ("d", "success"),
        ]
    )
    annotated = annotate_blocked(results, plan)
    assert [item.blocked_dependencies for item in annotated] == [2, 1, 0, 0]
    assert summarize_results(annotated, 4).blocked_producers == ("a", "b")


def test_fallback_examina_listas_e_descarta_campos_somente_leitura() -> None:
    inner = Schema(
        type="object",
        required=("ref", "readonly"),
        properties={
            "ref": Schema(type="string", pattern="[a-z]+"),
            "readonly": Schema(type="string", max_length=20, read_only=True),
        },
    )
    schema = Schema(type="object", properties={"items": Schema(type="array", items=inner)})
    op = Operation(
        operation_id="create",
        method="post",
        path="/things",
        request_body=RequestBody(
            media=(MediaBody(media_type="application/json", body_schema=schema),)
        ),
    )
    body: JsonValue = {"items": [{"ref": "x", "readonly": "y"}]}
    origins = {"body.items[0].ref": False, "body.items[0].readonly": False}
    assert conflict_fields(HttpResponse(status=409), op, body, origins) == ("items[0].ref",)
