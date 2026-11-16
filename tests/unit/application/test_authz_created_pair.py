"""Contrato da criação e leitura de pares sintéticos no authz."""

import json

import pytest

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.application import authz_checks_mass, authz_created_pair
from harness_dast.application.authz import Authz, AuthzRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.authz_config import AuthzCheck
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.authz_rig import AuthzRig, Clinic, clinic_spec
from tests.fakes.authz_write_rig import exchange, seed
from tests.fakes.probe_ports import InMemoryDocuments, reply
from tests.fakes.rig import INT, STR, operation, parameter


class Owned(Clinic):
    def __init__(self, path: str, *, exposed: bool, owner_read: bool = True) -> None:
        super().__init__()
        self.path = path
        self.exposed = exposed
        self.owner_read = owner_read
        self.resources: dict[str, tuple[str, dict[str, str]]] = {}

    def _route(self, request: HttpRequest, path: str, alias: str) -> HttpResponse:
        if path == self.path and request.method == "POST":
            body = json.loads(request.body or b"{}")
            key = str(len(self.resources) + 1)
            self.resources[key] = (alias, body)
            return reply(201, {"id": key})
        if path.startswith(self.path + "/") and request.method == "GET":
            key = path.rsplit("/", 1)[-1]
            item = self.resources.get(key)
            if item is None:
                return reply(404, {})
            owner, body = item
            if alias == owner and not self.owner_read:
                return reply(403, {})
            if alias != owner and not self.exposed:
                return reply(403, {})
            return reply(200, {"id": key, **body})
        return super()._route(request, path, alias)


def make_rig(path: str, *, exposed: bool, **kwargs: object) -> AuthzRig:
    api_path = "/" + path
    base = clinic_spec()
    spec = ApiSpec(
        title=base.title,
        version=base.version,
        servers=base.servers,
        operations=(
            *base.operations,
            operation(
                "createSynthetic",
                "post",
                api_path,
                body={"label": STR},
                required=("label",),
                produces={"id": INT},
            ),
            operation(
                "readSynthetic",
                "get",
                api_path + "/{id}",
                parameters=(parameter("id"),),
                produces={"id": INT, "label": STR},
            ),
        ),
    )
    return AuthzRig(
        Owned(path, exposed=exposed, owner_read=bool(kwargs.get("owner_read", True))),
        spec=spec,
        authz={
            "allow_writes": kwargs.get("allow_writes", True),
            "shared_roles": kwargs.get("shared_roles", []),
        },
    )


def execute(
    rig: AuthzRig, path: str, checks: tuple[AuthzCheck, ...] = ("horizontal",)
) -> AuthzResult:
    api_path = "/" + path
    probe = seed(
        rig,
        exchange(
            "createSynthetic", "POST", api_path, api_path, account="adm", body={"label": "old"}
        ),
        exchange("readSynthetic", "GET", api_path + "/{id}", api_path + "/999", account="adm"),
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
                }
            ],
        }
    )
    rig.documents = InMemoryDocuments(rules)
    usecase = Authz(
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
    return usecase.execute(AuthzRequest(product="agenda", run_id=probe.run_id, checks=checks))


@pytest.mark.parametrize("path", ["api/widgets", "api/records"])
@pytest.mark.parametrize("exposed", [True, False])
def test_created_object_read_only_by_other_account_when_exposed(path: str, exposed: bool) -> None:
    rig = make_rig(path, exposed=exposed)
    result = execute(rig, path)
    assert result.created_resources == 1
    assert bool(result.findings) is exposed
    assert isinstance(rig.clinic, Owned)
    assert next(iter(rig.clinic.resources.values()))[1]["label"] != "old"
    assert all(r.method != "DELETE" for r in rig.target.requests)


def test_without_write_authorization_does_not_create() -> None:
    rig = make_rig("api/widgets", exposed=True, allow_writes=False)
    result = execute(rig, "api/widgets")
    assert result.created_resources == 0
    assert any(n.reason == "writes_not_authorized" for n in result.not_tested)


def test_shared_role_does_not_create() -> None:
    rig = make_rig("api/widgets", exposed=True, shared_roles=["paciente"])
    result = execute(rig, "api/widgets")
    assert result.created_resources == 0
    assert any(n.reason == "shared_role" for n in result.not_tested)


def test_failed_owner_confirmation_is_not_a_finding() -> None:
    rig = make_rig("api/widgets", exposed=True, owner_read=False)
    result = execute(rig, "api/widgets")
    assert result.created_resources == 1
    assert not result.findings
    assert any(n.reason == "created_owner_read_failed" for n in result.not_tested)


def test_no_account_compared_when_reader_belongs_to_another_parent() -> None:
    from harness_dast.domain.authz_plan_created_pair import plan_created_pairs

    post = exchange(
        "make", "POST", "/api/groups/{group}/things", "/api/groups/1/things", body={"x": 1}
    )
    read = exchange("read", "GET", "/api/groups/{group}/things/{id}", "/api/groups/2/things/5")
    plan = plan_created_pairs(
        (post, read),
        {"a": "member", "b": "member"},
        frozenset(),
        (),
        frozenset(),
        allow_writes=True,
    )

    assert not plan.tasks
    assert [n.reason for n in plan.not_tested] == ["create_not_readable"]


def test_created_pair_and_mass_assignment_share_the_write_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(authz_created_pair, "MAX_MASS_REQUESTS", 1)
    monkeypatch.setattr(authz_checks_mass, "MAX_MASS_REQUESTS", 1)
    rig = make_rig("api/widgets", exposed=True)

    result = execute(rig, "api/widgets", ("horizontal", "mass_assignment"))

    posts = [
        r for r in rig.target.requests if r.operation_id.startswith("authz:") and r.method == "POST"
    ]
    assert len(posts) == 1
    assert any(
        n.check == "mass_assignment" and n.reason == "budget_exhausted" for n in result.not_tested
    )


def test_mass_post_reader_uses_the_creator_when_probe_used_another_account() -> None:
    rig = make_rig("api/widgets", exposed=True)
    probe = seed(
        rig,
        exchange("createSynthetic", "POST", "/api/widgets", "/api/widgets", body={"label": "old"}),
        exchange("readSynthetic", "GET", "/api/widgets/{id}", "/api/widgets/999", account="pac_b"),
    )

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )

    assert result.findings
    reads = [r for r in rig.target.requests if r.operation_id == "authz:readSynthetic"]
    assert reads
    assert all(r.account == "pac_a" for r in reads)
