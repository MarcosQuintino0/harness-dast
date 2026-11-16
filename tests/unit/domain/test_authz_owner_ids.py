"""Fontes de identidade aceitam só valores inequívocos, da conta e do tipo declarado."""

import json

import pytest

from harness_dast.domain.api_model import Operation, Parameter, SuccessResponse
from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.authz_owner_ids import (
    object_identity,
    owner_collection,
    owner_identity,
    owner_inventory,
    owner_parameter,
    recorded_owner_ids,
)
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.rig import INT, STR, operation, parameter

ITEM = operation("read", "get", "/api/records/{id}", parameters=(parameter("id"),))
PARAM = parameter("id")


def collection(**changes: object) -> Operation:
    data = {
        "operation_id": "list",
        "method": "get",
        "path": "/api/records",
        "success_responses": [
            SuccessResponse(
                status="200",
                body_schema=Schema(
                    type="array", items=Schema(type="object", properties={"id": INT})
                ),
            )
        ],
    }
    return Operation.model_validate({**data, **changes})


def exchange(**changes: object) -> ExchangeRecord:
    data = {
        "operation_id": "create",
        "method": "POST",
        "path": "/api/records",
        "target": "/api/records",
        "account": "a",
        "status": 200,
        "body": '{"id":11}',
    }
    return ExchangeRecord.model_validate({**data, **changes})


@pytest.mark.parametrize(
    ("value", "wanted"),
    [
        (11, "11"),
        ("11", None),
        (True, None),
        (None, None),
        ({"id": 11}, None),
        (1.2, None),
        (-1, "-1"),
    ],
)
def test_tipo_estrito_quando_identificador_inteiro(value: JsonValue, wanted: str | None) -> None:
    assert owner_identity(value, PARAM) == wanted


@pytest.mark.parametrize("value", ["", "a/b", "..", "a b", "%31", "é", "a" * 65, "a?x=1"])
def test_recusa_forma_ambigua_quando_identificador_textual(value: str) -> None:
    assert owner_identity(value, parameter("id", STR)) is None


@pytest.mark.parametrize(
    "value", [{}, {"id": "11"}, {"id": 11, "ID": 11}, {"id": 11, "recordId": 12}, []]
)
def test_recusa_objeto_quando_identidade_ausente_ou_contraditoria(value: JsonValue) -> None:
    assert object_identity(value, parameter("recordId")) is None


def test_identidade_quando_nome_do_parametro_ou_id_concordam() -> None:
    assert object_identity({"recordId": 11, "id": 11}, parameter("recordId")) == "11"
    assert object_identity({"recordId": 11}, parameter("recordId")) == "11"
    assert owner_identity("synthetic_title", parameter("title", STR)) == "synthetic_title"


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"null",
        b"{}",
        b"not json",
        b"[1]",
        b'[{"id":11},{"id":11}]',
        b'[{"id":11,"id":12}]',
        b'[{"id":false}]',
        b"\xff",
    ],
)
def test_recusa_inventario_quando_malformado_ou_ambiguo(body: bytes) -> None:
    assert owner_inventory(body, PARAM) is None


def test_inventario_quando_valido_vazio_ou_excessivo() -> None:
    assert owner_inventory(b'[{"id":12},{"id":11}]', PARAM) == ("11", "12")
    assert owner_inventory(b"[]", PARAM) == ()
    assert owner_inventory(json.dumps([{"id": n} for n in range(10001)]).encode(), PARAM) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"method": "post"},
        {"path": "/api/other"},
        {"parameters": [Parameter(name="filter", location="query", required=True)]},
        {"success_responses": []},
        {"success_responses": [SuccessResponse(status="200")]},
        {"success_responses": [SuccessResponse(status="200", body_schema=Schema(type="object"))]},
        {
            "success_responses": [
                SuccessResponse(status="200", body_schema=Schema(type="array", items=STR))
            ]
        },
        {
            "success_responses": [
                SuccessResponse(
                    status="200",
                    body_schema=Schema(
                        type="array", items=Schema(type="object", properties={"id": STR})
                    ),
                )
            ]
        },
    ],
)
def test_recusa_colecao_quando_contrato_nao_permite_leitura_de_dono(
    changes: dict[str, object],
) -> None:
    assert not owner_collection(collection(**changes), ITEM, PARAM)


def test_colecao_quando_filtro_opcional_nao_e_enviado() -> None:
    op = collection(parameters=[Parameter(name="filter", location="query", required=False)])
    assert owner_collection(op, ITEM, PARAM)


@pytest.mark.parametrize(
    "op",
    [
        operation("read", "get", "/api/records"),
        operation("read", "get", "/api/{parent}/records/{id}"),
        operation("read", "get", "/api/records/{id}/child"),
        operation("read", "get", "/api/records/{id}"),
        operation(
            "read", "get", "/api/records/{id}", parameters=(parameter("id", Schema(type="array")),)
        ),
        operation("read", "get", "/api/records/{token}", parameters=(parameter("token", STR),)),
        operation(
            "read",
            "get",
            "/api/records/{id}",
            parameters=(PARAM, parameter("filter", STR, "query")),
        ),
    ],
)
def test_leitor_nao_suportado_quando_marcador_ou_requisitos_ambiguos(op: Operation) -> None:
    assert owner_parameter(op) is None


def test_leitor_quando_parametro_final_valido() -> None:
    assert owner_parameter(ITEM) == PARAM


def test_fontes_quando_criacao_da_propria_conta_ja_sanitizada() -> None:
    assert recorded_owner_ids(ITEM, PARAM, "a", [exchange()]) == ("11",)
    assert recorded_owner_ids(ITEM, PARAM, "b", [exchange()]) == ()
    assert recorded_owner_ids(ITEM, PARAM, "a", [exchange(status=403)]) == ()
    assert recorded_owner_ids(ITEM, PARAM, "a", [exchange(body=None)]) == ()
    assert recorded_owner_ids(ITEM, PARAM, "a", [exchange(omitted_fields=("id",))]) is None
    assert recorded_owner_ids(ITEM, PARAM, "a", [exchange(body="{}")]) is None


@pytest.mark.parametrize(
    ("target", "wanted"),
    [
        ("/api/records/11", ("11",)),
        ("/api/records/01", None),
        ("/api/records/11?x=1", None),
        ("/api/other/11", None),
    ],
)
def test_fonte_quando_identificador_ja_esta_no_alvo_da_conta(
    target: str,
    wanted: tuple[str, ...] | None,
) -> None:
    e = exchange(method="PUT", path=ITEM.path, target=target)
    assert recorded_owner_ids(ITEM, PARAM, "a", [e]) == wanted


def test_fonte_quando_identificador_textual_no_alvo() -> None:
    op = operation("read", "get", "/api/records/{id}", parameters=(parameter("id", STR),))
    assert recorded_owner_ids(
        op,
        op.parameters[0],
        "a",
        [exchange(method="GET", path=op.path, target="/api/records/title")],
    ) == ("title",)
