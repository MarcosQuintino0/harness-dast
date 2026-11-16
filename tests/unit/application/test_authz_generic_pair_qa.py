"""Par automático com papéis, contas e contratos sintéticos genéricos."""

import json

import pytest

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.application.authz import Authz, AuthzRequest
from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.probe_exchange import ExchangeLog, ExchangeRecord
from harness_dast.domain.profile import ProductProfile
from tests.fakes.probe_ports import InMemoryDocuments, InMemorySpecs, reply
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.rig import INT, STR, Rig, operation, parameter
from tests.fakes.scan_ports import InMemoryRunArtifacts


@pytest.mark.parametrize("small_integer", [False, True])
def test_vinculo_e_unico_com_papel_e_contas_genericas(small_integer: bool) -> None:
    data = valid_profile_data("example")
    first = data["auth"]["accounts"][0]
    first.update({"alias": "owner_a", "role": "member"})
    second = {**first, "alias": "peer_b"}
    data["auth"]["accounts"] = [first, second]
    data["auth"]["token_response_field"] = "access_token"  # noqa: S105 - nome do campo
    data["authz"] = {"allow_writes": True}
    profile = ProductProfile.from_data(data)
    serial = Schema(type="integer", minimum=1, maximum=100) if small_integer else STR
    spec = ApiSpec(
        title="Example",
        version="1",
        servers=(profile.environment.base_url,),
        operations=(
            operation("login", "post", "/api/auth/login", secured=False),
            operation("makeGroup", "post", "/api/groups", produces={"id": INT}),
            operation(
                "create",
                "post",
                "/api/widgets",
                body={"group_id": INT, "serial": serial},
                required=("group_id", "serial"),
                produces={"id": INT},
            ),
            operation(
                "read",
                "get",
                "/api/widgets/{id}",
                parameters=(parameter("id"),),
                produces={"id": INT, "group_id": INT, "serial": serial},
            ),
        ),
    )
    objects: dict[str, dict[str, object]] = {}

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.url.endswith("/api/auth/login"):
            return reply(200, {"access_token": "generic-token"})
        if request.method == "POST" and request.url.endswith("/api/widgets"):
            body = json.loads(request.body or b"{}")
            key = str(len(objects) + 1)
            objects[key] = {"id": key, **body}
            return reply(201, {"id": key})
        if request.method == "GET" and "/api/widgets/" in request.url:
            found = objects.get(request.url.rsplit("/", 1)[-1])
            return reply(200, found) if found is not None else reply(404, {})
        return reply(200, {"id": 89})

    rig = Rig(profile=profile, spec=spec, handler=handler)
    probe = rig.probe().execute(ProbeRequest(product="example"))
    old_serial: str | int = 17 if small_integer else "old"
    old_body = {"group_id": 89, "serial": old_serial}
    exchanges = (
        ExchangeRecord(
            operation_id="create",
            method="POST",
            path="/api/widgets",
            target="/api/widgets",
            account="owner_a",
            status=201,
            content_type="application/json",
            body=json.dumps(old_body),
        ),
        ExchangeRecord(
            operation_id="read",
            method="GET",
            path="/api/widgets/{id}",
            target="/api/widgets/999",
            account="owner_a",
            status=200,
        ),
    )
    rig.store.exchanges[probe.run_id] = ExchangeLog(
        run_id=probe.run_id, product="example", exchanges=exchanges, next_unique_counter=0
    )
    rules = DataRules.from_data(
        {
            "schema_version": 1,
            "rules": [
                {
                    "match": {"field": "serial", "operation": "create"},
                    "generator": "integer" if small_integer else "alphanumeric",
                    "unique": True,
                }
            ],
        }
    )
    flows = FlowSpec.from_data(
        {
            "schema_version": 1,
            "bindings": [
                {
                    "produces": {"operation": "makeGroup", "field": "id"},
                    "consumed_by": [{"operation": "create", "field": "group_id"}],
                }
            ],
        }
    )
    service = Authz(
        profiles=rig.profiles,
        specs=InMemorySpecs(spec),
        documents=InMemoryDocuments(rules, flows),
        value_sources=GeneratorCatalogue,
        entropy=rig.entropy,
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        store=rig.store,
        artifacts=InMemoryRunArtifacts(rig.store),
        clock=rig.clock,
        sleeper=rig.clock,
    )

    result = service.execute(
        AuthzRequest(product="example", run_id=probe.run_id, checks=("horizontal",))
    )

    posts = [r for r in rig.target.requests if r.operation_id == "authz:pair:create"]
    assert len(posts) == 1, [n.reason for n in result.not_tested]
    body = json.loads(posts[0].body or b"{}")
    assert body["group_id"] == 89
    assert body["serial"] != old_serial
    if small_integer:
        assert 1 <= body["serial"] <= 100
    readers = [r.account for r in rig.target.requests if r.operation_id == "authz:pair:read"]
    assert readers == ["owner_a", "peer_b"]
    assert result.created_resources == 1
    assert any(f.technique == "authz_horizontal" for f in result.findings)
