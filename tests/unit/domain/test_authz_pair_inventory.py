"""Condições necessárias para inferir ausência visível em uma coleção."""

import json

import pytest

from harness_dast.domain.api_model import SuccessResponse
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.authz_pair_inventory import inventory_ids, supports_inventory
from harness_dast.domain.authz_pair_marker import marker_fields
from tests.fakes.authz_write_rig import exchange
from tests.fakes.rig import INT, STR, operation, parameter


def test_inventario_recusa_colisao_ou_item_sem_marcador() -> None:
    reader = exchange("read", "GET", "/items/{id}", "/items/1")
    for items in ([{"id": 3, "label": "marker"}], [{"id": 3}]):
        assert (
            inventory_ids(json.dumps(items).encode(), reader, "https://x", {"label": "marker"})
            is None
        )


def test_inventario_recusa_identificador_duplicado_no_json_original() -> None:
    reader = exchange("read", "GET", "/items/{id}", "/items/1")
    body = b'[{"id":1,"id":2,"label":"old"}]'
    assert inventory_ids(body, reader, "https://x", {"label": "new"}) is None


@pytest.mark.parametrize("maximum", [1, 20])
def test_inventario_com_limite_de_itens_declarado_e_recusado(maximum: int) -> None:
    schema = Schema(
        type="array",
        max_items=maximum,
        items=Schema(type="object", properties={"id": INT, "label": STR}),
    )
    listing = operation("list", "get", "/items").model_copy(
        update={"success_responses": (SuccessResponse(status="200", body_schema=schema),)}
    )
    reader = exchange("read", "GET", "/items/{id}", "/items/1")
    assert not supports_inventory(listing, reader, frozenset({"label"}))


def test_marcador_recusa_vinculos_credenciais_padrao_e_enumeracao() -> None:
    fields = {
        "label": STR,
        "related": STR,
        "password": STR,
        "choice": Schema(type="string", enum=("a", "b")),
        "pattern": Schema(type="string", pattern="x+"),
        "role": STR,
    }
    post = operation("create", "post", "/items", body=fields)
    read = operation("read", "get", "/items/{id}", parameters=(parameter("id"),), produces=fields)
    assert marker_fields(post, read, frozenset({"related"}), frozenset({"password"})) == (
        ("label", 0, None),
    )


@pytest.mark.parametrize("name", ["confidential_note", "private_value", "secret_annotation"])
def test_texto_sintetico_confidencial_pode_ser_marcador(name: str) -> None:
    fields = {name: STR}
    post = operation("create", "post", "/items", body=fields)
    read = operation("read", "get", "/items/{id}", parameters=(parameter("id"),), produces=fields)
    assert marker_fields(post, read, frozenset()) == ((name, 0, None),)


def test_campos_de_credencial_do_perfil_e_format_password_sao_recusados() -> None:
    fields = {"phrase": STR, "other": Schema(type="string", format="password")}
    post = operation("create", "post", "/items", body=fields)
    read = operation("read", "get", "/items/{id}", parameters=(parameter("id"),), produces=fields)
    assert marker_fields(post, read, frozenset(), frozenset({"phrase"})) == ()
