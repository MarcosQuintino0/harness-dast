"""Inventário visível anterior ao POST que recebe identificador do servidor."""

import json

import pytest

from harness_dast.domain.api_model import SuccessResponse
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.authz_rig import AuthzRig
from tests.fakes.authz_write_rig import exchange
from tests.fakes.probe_ports import FakeTarget, reply
from tests.fakes.rig import INT, STR, operation, parameter
from tests.unit.application.test_authz_created_pair import Owned, execute, make_rig


def inventory_rig(*, query: bool = False, incomplete: bool = False, status: int = 201) -> AuthzRig:
    rig = make_rig("api/widgets", exposed=True)
    create = operation(
        "createSynthetic",
        "post",
        "/api/widgets",
        body={"label": STR},
        required=("label",),
        produces={"id": INT},
    )
    collection = operation(
        "listSynthetic",
        "get",
        "/api/widgets",
        parameters=(parameter("page", location="query"),) if query else (),
    ).model_copy(
        update={
            "success_responses": (
                SuccessResponse(
                    status="200",
                    body_schema=Schema(
                        type="array",
                        items=Schema(type="object", properties={"id": INT, "label": STR}),
                    ),
                ),
            )
        }
    )
    rig.spec = rig.spec.model_copy(
        update={
            "operations": (
                *(
                    create if op.operation_id == "createSynthetic" else op
                    for op in rig.spec.operations
                ),
                collection,
            )
        }
    )
    delegate = rig.clinic
    assert isinstance(delegate, Owned)

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id == "authz:pair:listSynthetic":
            if incomplete:
                return reply(200, [{"label": "incomplete"}])
            return reply(
                200, [{"id": key, **body} for key, (_, body) in delegate.resources.items()]
            )
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        if request.operation_id == "authz:pair:createSynthetic":
            return response.model_copy(update={"status": status})
        return response

    rig.target = FakeTarget(handler)
    return rig


def list_exchange() -> ExchangeRecord:
    return exchange("listSynthetic", "GET", "/api/widgets", "/api/widgets", account="adm")


@pytest.mark.parametrize("status", [200, 201])
def test_server_id_with_visible_inventories_and_marker_is_compared(status: int) -> None:
    rig = inventory_rig(status=status)
    collection = list_exchange()
    result = execute(rig, "api/widgets", extra_exchanges=(collection,))
    assert result.findings
    reads = [r.account for r in rig.target.requests if r.operation_id == "authz:pair:listSynthetic"]
    assert reads == ["pac_a", "pac_b"]
    assert result.created_resources == 1


@pytest.mark.parametrize(("query", "incomplete"), [(True, False), (False, True)])
def test_invalid_inventory_is_not_used_for_creation(query: bool, incomplete: bool) -> None:
    rig = inventory_rig(query=query, incomplete=incomplete)
    collection = list_exchange()
    result = execute(rig, "api/widgets", extra_exchanges=(collection,))
    assert not result.findings
    assert not [r for r in rig.target.requests if r.operation_id == "authz:pair:createSynthetic"]
    assert any(
        n.reason in {"new_identifier_unavailable", "inventory_unavailable"}
        for n in result.not_tested
    )


def test_id_present_in_either_snapshot_does_not_prove_creation() -> None:
    rig = inventory_rig()
    collection = list_exchange()
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id == "authz:pair:listSynthetic":
            return reply(200, [{"id": "exists", "label": "old"}])
        if request.operation_id == "authz:pair:createSynthetic":
            return reply(200, {"id": "exists"})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    result = execute(rig, "api/widgets", extra_exchanges=(collection,))
    assert not result.findings
    assert any(n.reason == "created_target_preexisting" for n in result.not_tested)


@pytest.mark.parametrize("name", ["confidential_note", "private_value", "secret_annotation"])
def test_singleton_array_confirms_synthetic_marker_without_recording_value(name: str) -> None:
    rig = make_rig("api/widgets", exposed=True)
    create = operation(
        "createSynthetic",
        "post",
        "/api/widgets",
        body={"id": STR, name: STR},
        required=("id", name),
        produces={"id": INT},
    )
    read = operation("readSynthetic", "get", "/api/widgets/{id}", parameters=(parameter("id"),))
    read = read.model_copy(
        update={
            "success_responses": (
                SuccessResponse(
                    status="200",
                    body_schema=Schema(
                        type="array", items=Schema(type="object", properties={"id": INT, name: STR})
                    ),
                ),
            )
        }
    )
    rig.spec = rig.spec.model_copy(
        update={
            "operations": tuple(
                create
                if op.operation_id == "createSynthetic"
                else read
                if op.operation_id == "readSynthetic"
                else op
                for op in rig.spec.operations
            )
        }
    )
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        if request.operation_id == "authz:pair:readSynthetic" and response.status == 200:
            return reply(200, [json.loads(response.body)])
        return response

    rig.target = FakeTarget(handler)
    rules = DataRules.from_data(
        {
            "schema_version": 1,
            "rules": [
                {"match": {"field": "id"}, "generator": "alphanumeric", "unique": True},
                {"match": {"field": name}, "generator": "alphanumeric", "args": {"length": 12}},
            ],
        }
    )
    result = execute(rig, "api/widgets", rules_override=rules)
    posts = [r for r in rig.target.requests if r.operation_id == "authz:pair:createSynthetic"]
    marker = json.loads(posts[0].body or b"{}")[name]
    assert len(marker) == 12
    assert result.findings
    assert marker not in result.model_dump_json()


def test_singleton_array_requires_matching_resource_id() -> None:
    rig = make_rig("api/widgets", exposed=True)
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        if request.operation_id == "authz:pair:readSynthetic" and response.status == 200:
            return reply(200, [{**json.loads(response.body), "id": "different"}])
        return response

    rig.target = FakeTarget(handler)
    result = execute(rig, "api/widgets")
    assert not result.findings
    assert any(note.reason == "created_read_ambiguous" for note in result.not_tested)
