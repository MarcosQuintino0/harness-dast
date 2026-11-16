"""Revisão independente das provas para captura de conhecimento."""

from pathlib import Path
from typing import Literal

import pytest

from harness_dast.domain.errors import ConfigError
from tests.unit.application.test_knowledge_observations import EvidenceStore, _prepare


@pytest.mark.parametrize("tamper", ["alias", "rule_index", "generator", "operation"])
def test_v19_independent_rejects_forged_receipt_without_saving(
    tmp_path: Path, tamper: Literal["alias", "rule_index", "generator", "operation"]
) -> None:
    capture, evidence, _ = _prepare(tmp_path)
    operations = list(evidence.probe.operations)
    target = operations[0]
    assert target.rule_uses
    if tamper == "alias":
        changed = target.model_copy(update={"account": "other-account"})
    else:
        name, value = {
            "rule_index": ("rule_index", 9),
            "generator": ("generator", "wrong"),
            "operation": ("operation", "other"),
        }[tamper]
        forged = target.rule_uses[0].model_copy(update={name: value})
        changed = target.model_copy(update={"rule_uses": (forged,)})
    operations[0] = changed
    store = capture._runs
    assert isinstance(store, EvidenceStore)
    store.evidence = evidence.model_copy(
        update={"probe": evidence.probe.model_copy(update={"operations": tuple(operations)})}
    )

    with pytest.raises(ConfigError):
        capture.execute("agenda", evidence.provenance.run_id)

    assert not (tmp_path / "agenda" / "knowledge.captured.yml").exists()


@pytest.mark.parametrize("tamper", ["other_run", "stale_hash"])
def test_v19_independent_rejects_wrong_run_or_stale_hash_before_capture(
    tmp_path: Path, tamper: Literal["other_run", "stale_hash"]
) -> None:
    capture, evidence, _ = _prepare(tmp_path)
    if tamper == "other_run":
        manifest = evidence.manifest.model_copy(update={"run_id": "other-run"})
    else:
        hashes = evidence.manifest.hashes.model_copy(update={"openapi": "0" * 64})
        manifest = evidence.manifest.model_copy(update={"hashes": hashes})
    store = capture._runs
    assert isinstance(store, EvidenceStore)
    store.evidence = evidence.model_copy(update={"manifest": manifest})

    with pytest.raises(ConfigError):
        capture.execute("agenda", evidence.provenance.run_id)

    assert not (tmp_path / "agenda" / "knowledge.captured.yml").exists()


def test_v19_independent_post_readback_refutes_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    from harness_dast.domain.http_messages import HttpRequest, HttpResponse
    from tests.fakes.probe_ports import reply
    from tests.unit.application import test_authz_effect_reuse as support

    class EchoButIgnore(support.Objects):
        def _route(self, request: HttpRequest, path: str, alias: str) -> HttpResponse:
            if path == "api/submissions" and request.method == "POST":
                key = str(len(self.objects) + 1)
                self.objects[key] = {"id": key, "balance": 0}
                return reply(201, {"id": key, "balance": 5})
            return super()._route(request, path, alias)

    monkeypatch.setattr(support, "Objects", EchoButIgnore)
    rig, result = support._run(True)
    assert any(
        r.operation_id == "authz:effect_recipe_after:readObject" for r in rig.target.requests
    )
    assert not result.findings
    assert not result.effects


@pytest.mark.parametrize("before", [10, 11])
def test_v19_independent_put_readback_refutes_echo_or_preexisting(before: int) -> None:
    from harness_dast.application.authz import Authz, AuthzRequest
    from harness_dast.domain.http_messages import HttpRequest, HttpResponse
    from harness_dast.domain.knowledge import KnowledgeEffect
    from tests.fakes.authz_rig import Clinic
    from tests.fakes.authz_write_rig import exchange, seed
    from tests.fakes.probe_ports import FakeTarget, reply
    from tests.fakes.rig import INT, operation, parameter
    from tests.unit.application.test_authz_mass_derived import derived_rig

    rig = derived_rig(
        Clinic(),
        derive_mass_candidates=False,
        mass_assignment_fields=[{"name": "saldo", "value": 11}],
    )
    reader = operation(
        "readAlternative",
        "get",
        "/api/{part}",
        parameters=(parameter("part"),),
        produces={"saldo": INT},
    )
    rig.spec = rig.spec.model_copy(update={"operations": (*rig.spec.operations, reader)})
    probe = seed(
        rig,
        exchange(
            "atualizarPerfil", "PUT", "/api/me", "/api/me", account="pac_a", body={"nome": "x"}
        ),
        exchange("readAlternative", "GET", "/api/{part}", "/api/me", account="pac_a"),
    )
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id in (
            "authz:effect_recipe_before:readAlternative",
            "authz:effect_recipe_after:readAlternative",
        ):
            return reply(200, {"saldo": before})
        if request.operation_id == "authz:atualizarPerfil":
            return reply(200, {"saldo": 11})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    recipe = KnowledgeEffect(
        write_operation="atualizarPerfil",
        read_operation="readAlternative",
        account="pac_a",
        fields=("saldo",),
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
        effect_loader=lambda _product, _profile: (recipe,),
    )
    result = service.execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )
    assert any(
        r.operation_id == "authz:effect_recipe_before:readAlternative" for r in rig.target.requests
    )
    assert not result.findings
    assert not result.effects
