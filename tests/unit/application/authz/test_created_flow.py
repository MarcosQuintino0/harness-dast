"""Referências declaradas são preservadas ao criar dados novos para o par."""

import json

import pytest

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.application.authz.service import Authz, AuthzRequest
from harness_dast.domain.authz.flow_bindings import bindings_from_proven_body
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import TargetError
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.authz.write_rig import exchange, seed
from tests.fakes.probe_ports import FakeTarget, InMemoryDocuments, reply
from tests.fakes.rig import INT, STR, operation
from tests.unit.application.authz.test_created_pair import make_rig


def flow(field: str = "reference") -> FlowSpec:
    return FlowSpec.from_data(
        {
            "schema_version": 1,
            "bindings": [
                {
                    "produces": {"operation": "readSynthetic", "field": "id"},
                    "consumed_by": [{"operation": "createSynthetic", "field": field}],
                }
            ],
        }
    )


def test_nested_reference_is_extracted_and_other_values_are_not_bound() -> None:
    result = bindings_from_proven_body(
        flow("links.owner"),
        "createSynthetic",
        {
            "links": {"owner": 42},
            "label": "old",
        },
    )

    assert result.fields == {"links.owner": 42}


@pytest.mark.parametrize("body", [{}, {"reference": True}, {"reference": [1]}])
def test_absent_or_invalid_reference_is_not_invented(body: dict[str, object]) -> None:
    with pytest.raises(TargetError):
        bindings_from_proven_body(flow(), "createSynthetic", body)  # type: ignore[arg-type]  # dados externos inválidos


@pytest.mark.parametrize("path", ["api/widgets", "api/records"])
def test_creation_reuses_only_proven_reference_and_generates_new_data(path: str) -> None:
    rig = make_rig(path, exposed=True)
    api = "/" + path
    replacement = operation(
        "createSynthetic",
        "post",
        api,
        body={"label": STR, "reference": INT, "id": STR},
        required=("label", "reference", "id"),
        produces={"id": INT},
    )
    rig.spec = rig.spec.model_copy(
        update={
            "operations": tuple(
                replacement if op.operation_id == "createSynthetic" else op
                for op in rig.spec.operations
            )
        }
    )
    probe = seed(
        rig,
        exchange("createSynthetic", "POST", api, api, body={"label": "old", "reference": 73}),
        exchange("readSynthetic", "GET", api + "/{id}", api + "/999"),
    )
    rules = DataRules.from_data(
        {
            "schema_version": 1,
            "rules": [
                {
                    "match": {"field": "label"},
                    "generator": "alphanumeric",
                    "args": {"length": 16},
                    "unique": True,
                },
                {"match": {"field": "id"}, "generator": "alphanumeric", "unique": True},
            ],
        }
    )
    rig.documents = InMemoryDocuments(rules, flow())
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if (
            request.operation_id.startswith("authz:pair:")
            and request.method == "POST"
            and json.loads(request.body or b"{}").get("reference") != 73
        ):
            return reply(422, {})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    stage = Authz(
        profiles=rig.profiles,
        specs=rig._specs(),
        documents=rig.documents,
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
    result = stage.execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("horizontal",))
    )

    posts = [
        r
        for r in rig.target.requests
        if r.operation_id.startswith("authz:pair:") and r.method == "POST"
    ]
    assert posts
    body = json.loads(posts[0].body or b"{}")
    assert body["reference"] == 73
    assert body["label"] != "old"
    assert result.created_resources == 1
    assert result.findings


def test_old_exchange_log_without_counter_does_not_create() -> None:
    rig = make_rig("api/widgets", exposed=True)
    probe = seed(
        rig,
        exchange("createSynthetic", "POST", "/api/widgets", "/api/widgets", body={"label": "old"}),
        exchange("readSynthetic", "GET", "/api/widgets/{id}", "/api/widgets/999"),
    )
    log = rig.store.exchanges[probe.run_id]
    rig.store.exchanges[probe.run_id] = log.model_copy(update={"next_unique_counter": None})
    stage = Authz(
        profiles=rig.profiles,
        specs=rig._specs(),
        documents=rig.documents,
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

    result = stage.execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("horizontal",))
    )

    assert result.created_resources == 0
    assert any(note.reason == "new_data_unavailable" for note in result.not_tested)
    assert not [
        r
        for r in rig.target.requests
        if r.operation_id.startswith("authz:pair:") and r.method == "POST"
    ]
