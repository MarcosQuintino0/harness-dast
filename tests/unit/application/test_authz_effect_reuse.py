"""Uso efetivo de receita de releitura sem acrescentar candidato ou escrita."""

import json

from harness_dast.application.authz import Authz, AuthzRequest
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.knowledge import KnowledgeEffect
from tests.fakes.authz_rig import AuthzRig, Clinic, clinic_spec
from tests.fakes.authz_write_rig import exchange, seed
from tests.fakes.probe_ports import reply
from tests.fakes.rig import INT, STR, operation, parameter


class Objects(Clinic):
    def __init__(self, *, reveal: bool = True) -> None:
        super().__init__()
        self.reveal = reveal
        self.objects: dict[str, dict[str, JsonValue]] = {"1": {"id": "1", "balance": 0}}

    def _route(self, request: HttpRequest, path: str, alias: str) -> HttpResponse:
        if path == "api/submissions" and request.method == "POST":
            body = json.loads(request.body or b"{}")
            key = str(len(self.objects) + 1)
            self.objects[key] = {"id": key, "balance": body.get("balance", 0)}
            return reply(201, self.objects[key])
        if path.startswith("api/objects/") and request.method == "GET":
            value = self.objects.get(path.rsplit("/", 1)[-1])
            if value is not None and not self.reveal:
                return reply(200, {"id": value["id"]})
            return reply(200, value) if value is not None else reply(404, {})
        return super()._route(request, path, alias)


def _run(use_recipe: bool, *, reveal: bool = True) -> tuple[AuthzRig, AuthzResult]:
    base = clinic_spec()
    spec = base.model_copy(
        update={
            "operations": (
                *base.operations,
                operation(
                    "submit",
                    "post",
                    "/api/submissions",
                    body={"label": STR},
                    required=("label",),
                    produces={"id": INT, "balance": INT},
                ),
                operation(
                    "readObject",
                    "get",
                    "/api/objects/{id}",
                    parameters=(parameter("id"),),
                    produces={"id": INT, "balance": INT},
                ),
            )
        }
    )
    rig = AuthzRig(
        Objects(reveal=reveal),
        spec=spec,
        authz={
            "allow_writes": True,
            "mass_assignment_methods": ["POST"],
            "derive_mass_candidates": False,
            "mass_assignment_fields": [{"name": "balance", "value": 5}],
        },
    )
    probe = seed(
        rig,
        exchange(
            "submit",
            "POST",
            "/api/submissions",
            "/api/submissions",
            account="pac_a",
            body={"label": "old"},
        ),
        exchange("readObject", "GET", "/api/objects/{id}", "/api/objects/1", account="pac_a"),
    )
    recipe = KnowledgeEffect(
        write_operation="submit",
        read_operation="readObject",
        account="pac_a",
        fields=("balance",),
        proof="readback_verified",
    )
    service = Authz(
        profiles=rig.profiles,
        specs=rig._specs(),
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        store=rig.store,
        artifacts=rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
        effect_loader=(lambda _product, _profile: (recipe,)) if use_recipe else None,
    )
    return rig, service.execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )


def test_receita_ativa_releitura_provada_sem_nova_escrita() -> None:
    baseline, original = _run(False)
    updated, result = _run(True)
    baseline_posts = [r for r in baseline.target.requests if r.operation_id == "authz:submit"]
    updated_posts = [r for r in updated.target.requests if r.operation_id == "authz:submit"]
    reads = [
        r
        for r in updated.target.requests
        if r.operation_id == "authz:effect_recipe_after:readObject"
    ]
    assert len(baseline_posts) == len(updated_posts) == 1
    assert not [r for r in baseline.target.requests if r.operation_id == "authz:readObject"]
    assert len(reads) == 1
    assert reads[0].account == "pac_a"
    assert original.findings
    assert result.findings
    assert result.effects
    assert result.effects[0].read_operation == "readObject"


def test_leitura_sem_efeito_nao_usa_echo_para_inventar_achado() -> None:
    _, baseline = _run(False, reveal=False)
    _, result = _run(True, reveal=False)
    assert baseline.findings
    assert not result.findings
    assert result.effects == ()
