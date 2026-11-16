"""QA independente: encadeamento e unicidade em contrato sintético."""

import json

import pytest

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.application.authz import Authz, AuthzRequest
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.authz_write_rig import exchange, seed
from tests.fakes.probe_ports import FakeTarget, InMemoryDocuments
from tests.fakes.rig import INT, STR, operation
from tests.unit.application.test_authz_created_pair import make_rig


@pytest.mark.parametrize("small_integer", [False, True])
def test_criacao_reutiliza_vinculo_e_gera_dados_novos(small_integer: bool) -> None:
    rig = make_rig("api/widgets", exposed=True)
    serial_schema = Schema(type="integer", minimum=1, maximum=100) if small_integer else STR
    create = operation(
        "createSynthetic",
        "post",
        "/api/widgets",
        body={"group_id": INT, "id": serial_schema, "nonce": STR},
        required=("group_id", "id", "nonce"),
        produces={"id": INT},
    )
    producer = operation("makeGroup", "post", "/api/groups", produces={"id": INT})
    rig.spec = rig.spec.model_copy(
        update={
            "operations": (
                *(
                    create if op.operation_id == "createSynthetic" else op
                    for op in rig.spec.operations
                ),
                producer,
            )
        }
    )
    old = {"group_id": 89, "id": 17 if small_integer else "old", "nonce": "old"}
    probe = seed(
        rig,
        exchange("createSynthetic", "POST", "/api/widgets", "/api/widgets", body=old),
        exchange("readSynthetic", "GET", "/api/widgets/{id}", "/api/widgets/999"),
    )
    if small_integer:
        log = rig.store.exchanges[probe.run_id]
        assert log.next_unique_counter is not None
        old["id"] = 1 + (int(probe.run_id.rsplit("-", 1)[-1], 16) + log.next_unique_counter) % 100
        first = log.exchanges[0].model_copy(update={"body": json.dumps(old)})
        rig.store.exchanges[probe.run_id] = log.model_copy(
            update={"exchanges": (first, *log.exchanges[1:])}
        )
    rules = DataRules.from_data(
        {
            "schema_version": 1,
            "rules": [
                {
                    "match": {"field": "id", "operation": "createSynthetic"},
                    "generator": "integer" if small_integer else "alphanumeric",
                    "unique": True,
                },
                {"match": {"field": "nonce"}, "generator": "alphanumeric", "unique": True},
            ],
        }
    )
    flows = FlowSpec.from_data(
        {
            "schema_version": 1,
            "bindings": [
                {
                    "produces": {"operation": "makeGroup", "field": "id"},
                    "consumed_by": [{"operation": "createSynthetic", "field": "group_id"}],
                }
            ],
        }
    )
    documents = InMemoryDocuments(rules, flows)
    prior_counter = rig.store.exchanges[probe.run_id].next_unique_counter
    recorded: list[int | None] = []
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id == "authz:pair:createSynthetic" and request.method == "POST":
            recorded.append(rig.store.exchanges[probe.run_id].next_unique_counter)
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    service = Authz(
        profiles=rig.profiles,
        specs=rig._specs(),
        documents=documents,
        value_sources=GeneratorCatalogue,
        entropy=rig.entropy,
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        store=rig.store,
        artifacts=rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
    )

    result = service.execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("horizontal",))
    )

    posts = [r for r in rig.target.requests if r.operation_id == "authz:pair:createSynthetic"]
    assert len(posts) == 1, [n.reason for n in result.not_tested]
    body = json.loads(posts[0].body or b"{}")
    assert body["group_id"] == 89
    if small_integer:
        assert 1 <= body["id"] <= 100
    assert body["id"] != old["id"]
    assert result.created_resources == 1
    assert prior_counter is not None
    assert recorded[0] is not None
    assert recorded[0] > prior_counter

    first_counter = rig.store.exchanges[probe.run_id].next_unique_counter
    second = service.execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("horizontal",))
    )
    all_posts = [r for r in rig.target.requests if r.operation_id == "authz:pair:createSynthetic"]
    assert len(all_posts) == 2
    assert json.loads(all_posts[1].body or b"{}")["id"] != body["id"]
    assert first_counter is not None
    next_counter = rig.store.exchanges[probe.run_id].next_unique_counter
    assert next_counter is not None
    assert next_counter > first_counter
    assert second.created_resources == 1
