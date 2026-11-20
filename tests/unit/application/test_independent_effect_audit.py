"""Prova observável da aplicação da receita de efeito, sem rede real."""

from harness_dast.application.authz.service import Authz, AuthzRequest
from harness_dast.domain.knowledge import KnowledgeEffect
from tests.fakes.authz.rig import Clinic
from tests.fakes.authz.write_rig import exchange, seed
from tests.fakes.rig import INT, operation, parameter
from tests.unit.application.authz.test_mass_derived import derived_rig


def test_receita_com_efeito_provado_identifica_leituras_na_auditoria() -> None:
    rig = derived_rig(
        Clinic(stores=("saldo",)),
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

    assert result.effects == ()
    assert result.findings
    entries = [entry for entry in rig.store.all_audit() if entry.phase == "result"]
    before = next(
        e for e in entries if e.operation_id == "authz:effect_recipe_before:readAlternative"
    )
    write = next(e for e in entries if e.operation_id == "authz:atualizarPerfil")
    after = next(
        e for e in entries if e.operation_id == "authz:effect_recipe_after:readAlternative"
    )
    assert before.method == after.method == "GET"
    assert before.account == after.account == "pac_a"
    assert before.status == after.status == 200
    assert before.seq < write.seq < after.seq
