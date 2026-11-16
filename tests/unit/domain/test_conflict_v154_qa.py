"""Casos independentes de conflitos e dependências da V1.5.4."""

from harness_dast.domain.api_model import MediaBody, Operation, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.http_messages import HttpResponse
from harness_dast.domain.probe_conflict import annotate_blocked, conflict_fields
from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.probe_result import OperationResult


def test_conflito_ignora_campo_hostil_e_preserva_origem_e_leitura() -> None:
    schema = Schema(
        type="object",
        required=("serial", "handle", "readonly"),
        properties={
            "serial": Schema(type="string", max_length=20),
            "handle": Schema(type="string", max_length=20),
            "readonly": Schema(type="string", max_length=20, read_only=True),
        },
    )
    op = Operation(
        operation_id="criar",
        method="post",
        path="/itens",
        request_body=RequestBody(
            media=(MediaBody(media_type="application/json", body_schema=schema),)
        ),
    )
    response = HttpResponse(status=409, body=b'{"errors":[{"field":"<script>"}]}')
    fields = conflict_fields(
        response,
        op,
        {"serial": "a", "handle": "b", "readonly": "c"},
        {"body.serial": False, "body.handle": True, "body.readonly": False},
    )
    assert fields == ("serial",)


def test_grafo_com_dois_produtores_conta_cada_descendente_uma_vez() -> None:
    deps = {
        "primeiro": (),
        "segundo": (),
        "meio": ("primeiro", "segundo"),
        "fim": ("primeiro", "meio"),
    }
    plan = tuple(
        PlannedOperation(operation_id=k, method="POST", path="/x", decision="send", depends_on=v)
        for k, v in deps.items()
    )
    results = tuple(
        OperationResult(
            operation_id=k,
            method="POST",
            path="/x",
            outcome="conflict" if not v else "skipped_dependency",
        )
        for k, v in deps.items()
    )
    actual = {r.operation_id: r.blocked_dependencies for r in annotate_blocked(results, plan)}
    assert actual == {"primeiro": 2, "segundo": 2, "meio": 1, "fim": 0}
