"""Captura de receitas observadas com provas locais e rejeição de fontes divergentes."""

from pathlib import Path

import pytest

from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeStore
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.application.knowledge_capture import CaptureKnowledge
from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge import Knowledge, KnowledgeProvenance
from harness_dast.domain.knowledge_evidence import KnowledgeRunEvidence
from tests.fakes.approvals import InMemoryApprovalStore, approval_for
from tests.fakes.probe_ports import InMemorySpecs
from tests.fakes.rig import Rig, agenda_flows
from tests.unit.api_helpers import rule, rules_from


class EvidenceStore:
    def __init__(self, evidence: KnowledgeRunEvidence) -> None:
        self.evidence = evidence

    def read(self, run_id: str) -> KnowledgeRunEvidence:
        assert run_id == self.evidence.provenance.run_id
        return self.evidence


def _prepare(tmp_path: Path) -> tuple[CaptureKnowledge, KnowledgeRunEvidence, Rig]:
    rig = Rig(
        flows=agenda_flows(), rules=rules_from(rule("nome", "alphanumeric", operation="criar"))
    )
    result = rig.probe().execute(ProbeRequest(product="agenda", only=("buscar",)))
    manifest = rig.store.manifests[result.run_id][-1]
    evidence = KnowledgeRunEvidence(
        manifest=manifest,
        probe=result,
        provenance=KnowledgeProvenance(
            run_id=result.run_id, manifest_sha256="a" * 64, probe_sha256="b" * 64
        ),
    )
    (tmp_path / "agenda").mkdir()
    (tmp_path / "agenda" / "openapi.json").write_text("{}", encoding="utf-8")
    approvals = InMemoryApprovalStore()
    approvals.write(approval_for(rig.profile))
    capture = CaptureKnowledge(
        rig.profiles,
        FileKnowledgeStore(tmp_path),
        FileStrategyRepository(tmp_path),
        approvals,
        rig.clock,
        rig.documents,
        InMemorySpecs(rig.spec),
        rig.zap,
        "http://127.0.0.1:8080",
        EvidenceStore(evidence),
    )
    return capture, evidence, rig


def test_captura_receitas_de_2xx_com_proveniencia_sem_valores(tmp_path: Path) -> None:
    capture, evidence, _ = _prepare(tmp_path)
    capture.execute("agenda", evidence.provenance.run_id)
    raw = (tmp_path / "agenda" / "knowledge.captured.yml").read_text(encoding="utf-8")
    import yaml

    knowledge = Knowledge.from_data(yaml.safe_load(raw))
    assert knowledge.provenance == evidence.provenance
    assert knowledge.observed_accounts == ("user_a",)
    assert knowledge.observed_rules[0].operation == "criar"
    assert knowledge.observed_flows[0].consumer == "buscar"
    assert next(e for e in knowledge.entries if e.kind == "effect").state == "proposed"
    assert "access_token" not in raw
    assert "pacientes/7" not in raw


def test_captura_recusa_manifesto_desatualizado(tmp_path: Path) -> None:
    capture, evidence, _ = _prepare(tmp_path)
    store = capture._runs
    assert isinstance(store, EvidenceStore)
    store.evidence = evidence.model_copy(
        update={"manifest": evidence.manifest.model_copy(update={"zap_version": "outro"})}
    )
    with pytest.raises(ConfigError):
        capture.execute("agenda", evidence.provenance.run_id)
    assert not (tmp_path / "agenda" / "knowledge.captured.yml").exists()


def test_knowledge_recusa_estado_observado_sem_proveniencia(tmp_path: Path) -> None:
    capture, evidence, _ = _prepare(tmp_path)
    capture.execute("agenda", evidence.provenance.run_id)
    import yaml

    data = yaml.safe_load(
        (tmp_path / "agenda" / "knowledge.captured.yml").read_text(encoding="utf-8")
    )
    data["provenance"] = None
    with pytest.raises(ConfigError):
        Knowledge.from_data(data)


def test_receita_reutilizada_valida_regra_atual_e_recusa_falsificacao(tmp_path: Path) -> None:
    import yaml

    from harness_dast.application.knowledge import ExecutableKnowledge

    capture, evidence, rig = _prepare(tmp_path)
    capture.execute("agenda", evidence.provenance.run_id)
    folder = tmp_path / "agenda"
    (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")
    store = FileKnowledgeStore(tmp_path)
    service = ExecutableKnowledge(store, FileStrategyRepository(tmp_path), rig.clock, rig.zap)
    rules = rig.documents.load_data_rules("agenda")
    assert rules is not None
    recipes = service.validate(
        "agenda", rig.profile, rig.spec, rules, rig.documents.load_flows("agenda")
    )
    assert [(item.operation, item.rule_index) for item in recipes] == [("criar", 0)]
    source = folder / "knowledge.yml"
    forged = yaml.safe_load(source.read_text(encoding="utf-8"))
    forged["observed_rules"][0]["rule_index"] = 1
    source.write_text(yaml.safe_dump(forged), encoding="utf-8")
    with pytest.raises(ConfigError):
        service.validate("agenda", rig.profile, rig.spec, rules, rig.documents.load_flows("agenda"))


def test_campos_sem_prova_ficam_propostos_sem_reduzir_fluxo(tmp_path: Path) -> None:
    from harness_dast.application.knowledge import ExecutableKnowledge

    capture, evidence, rig = _prepare(tmp_path)
    without_rules = tuple(
        item.model_copy(update={"rule_uses": ()}) for item in evidence.probe.operations
    )
    store = capture._runs
    assert isinstance(store, EvidenceStore)
    store.evidence = evidence.model_copy(
        update={"probe": evidence.probe.model_copy(update={"operations": without_rules})}
    )
    capture.execute("agenda", evidence.provenance.run_id)
    folder = tmp_path / "agenda"
    (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")
    service = ExecutableKnowledge(
        FileKnowledgeStore(tmp_path), FileStrategyRepository(tmp_path), rig.clock, rig.zap
    )
    rules = rig.documents.load_data_rules("agenda")
    assert rules is not None
    assert (
        service.validate("agenda", rig.profile, rig.spec, rules, rig.documents.load_flows("agenda"))
        == ()
    )


def test_probe_reaplica_receita_validada_e_preserva_trabalho_planejado(tmp_path: Path) -> None:
    from harness_dast.adapters.datagen import GeneratorCatalogue
    from harness_dast.application.knowledge import ExecutableKnowledge, KnowledgeProfiles
    from harness_dast.application.probe import Probe

    capture, evidence, old_rig = _prepare(tmp_path)
    capture.execute("agenda", evidence.provenance.run_id)
    folder = tmp_path / "agenda"
    (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")
    rules = old_rig.documents.load_data_rules("agenda")
    assert rules is not None
    rig = Rig(rules=rules, flows=agenda_flows())
    knowledge_store = FileKnowledgeStore(tmp_path)
    dependencies = FileStrategyRepository(tmp_path)
    profiles = KnowledgeProfiles(rig.profiles, knowledge_store, dependencies, rig.clock, rig.zap)
    probe = Probe(
        profiles=profiles,
        specs=InMemorySpecs(rig.spec),
        documents=rig.documents,
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        zap=rig.zap,
        store=rig.store,
        clock=rig.clock,
        sleeper=rig.clock,
        entropy=rig.entropy,
        value_sources=GeneratorCatalogue,
        harness_version="test",
        knowledge_recipes=ExecutableKnowledge(knowledge_store, dependencies, rig.clock, rig.zap),
    )
    result = probe.execute(ProbeRequest(product="agenda", only=("buscar",)))
    assert [item.operation_id for item in result.operations] == ["criar", "buscar"]
    assert result.operations[0].rule_uses[0].rule_index == 0
    assert result.operations[1].flow_uses[0].producer == "criar"
    assert all(item.outcome == "success" for item in result.operations)


def test_captura_e_carrega_receita_de_efeito_sem_valor(tmp_path: Path) -> None:
    import yaml

    from harness_dast.application.knowledge import load_validated_effects
    from harness_dast.domain.knowledge import KnowledgeEffect

    capture, evidence, rig = _prepare(tmp_path)
    store = capture._runs
    assert isinstance(store, EvidenceStore)
    receipt = KnowledgeEffect(
        write_operation="criar",
        read_operation="buscar",
        account="user_a",
        fields=("nome",),
        proof="readback_verified",
    )
    provenance = evidence.provenance.model_copy(update={"authz_sha256": "c" * 64})
    store.evidence = evidence.model_copy(
        update={
            "effects": (receipt,),
            "provenance": provenance,
            "authz_product": "agenda",
            "authz_run_id": evidence.provenance.run_id,
            "authz_status": "completed",
            "authz_dry_run": False,
        }
    )
    capture.execute("agenda", evidence.provenance.run_id)
    folder = tmp_path / "agenda"
    saved = folder / "knowledge.captured.yml"
    document = yaml.safe_load(saved.read_text(encoding="utf-8"))
    assert document["effects"][0]["proof"] == "readback_verified"
    saved.rename(folder / "knowledge.yml")
    result = load_validated_effects(
        "agenda",
        rig.profile,
        FileKnowledgeStore(tmp_path),
        FileStrategyRepository(tmp_path),
        rig.clock,
        rig.zap,
    )
    assert result == (receipt,)
    (folder / "openapi.json").write_text('{"changed": true}', encoding="utf-8")
    assert (
        load_validated_effects(
            "agenda",
            rig.profile,
            FileKnowledgeStore(tmp_path),
            FileStrategyRepository(tmp_path),
            rig.clock,
            rig.zap,
        )
        == ()
    )


def test_captura_recusa_efeito_com_campo_inexistente(tmp_path: Path) -> None:
    from harness_dast.domain.knowledge import KnowledgeEffect

    capture, evidence, _ = _prepare(tmp_path)
    store = capture._runs
    assert isinstance(store, EvidenceStore)
    receipt = KnowledgeEffect(
        write_operation="criar",
        read_operation="buscar",
        account="user_a",
        fields=("campo_inexistente",),
        proof="readback_verified",
    )
    provenance = evidence.provenance.model_copy(update={"authz_sha256": "c" * 64})
    store.evidence = evidence.model_copy(
        update={
            "effects": (receipt,),
            "provenance": provenance,
            "authz_product": "agenda",
            "authz_run_id": evidence.provenance.run_id,
            "authz_status": "completed",
            "authz_dry_run": False,
        }
    )
    with pytest.raises(ConfigError):
        capture.execute("agenda", evidence.provenance.run_id)
