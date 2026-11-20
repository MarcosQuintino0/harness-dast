"""Captura e revalidação local das referências de conhecimento."""

from pathlib import Path

import pytest

from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeStore
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.application.knowledge import KnowledgeProfiles
from harness_dast.application.knowledge_capture import CaptureKnowledge
from harness_dast.domain.errors import ConfigError, ScopeNotApproved
from tests.fakes.approvals import InMemoryApprovalStore, approval_for
from tests.fakes.probe_ports import InMemorySpecs
from tests.fakes.rig import Rig


def _setup(tmp_path: Path, *, approved: bool = True) -> tuple[CaptureKnowledge, Rig]:
    rig = Rig()
    folder = tmp_path / "agenda"
    folder.mkdir()
    (folder / "openapi.json").write_text("{}", encoding="utf-8")
    approvals = InMemoryApprovalStore()
    if approved:
        approvals.write(approval_for(rig.profile))
    return CaptureKnowledge(
        rig.profiles,
        FileKnowledgeStore(tmp_path),
        FileStrategyRepository(tmp_path),
        approvals,
        rig.clock,
        rig.documents,
        InMemorySpecs(rig.spec),
        rig.zap,
        "http://127.0.0.1:8080",
    ), rig


def _validate_captured(folder: Path) -> None:
    """Simula a captura com recibos de uma rodada: promove as entradas de contrato a validadas."""
    import yaml

    path = folder / "knowledge.captured.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for entry in data["entries"]:
        if entry["kind"] != "effect":
            entry["state"] = "validated"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_captura_e_reuso_validam_fontes_sem_pedido(tmp_path: Path) -> None:
    capture, rig = _setup(tmp_path)
    result = capture.execute("agenda")
    folder = tmp_path / "agenda"
    _validate_captured(folder)
    assert result["activated"] is False
    assert not (folder / "knowledge.yml").exists()
    (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")
    profiles = KnowledgeProfiles(
        rig.profiles,
        FileKnowledgeStore(tmp_path),
        FileStrategyRepository(tmp_path),
        rig.clock,
        rig.zap,
    )
    assert profiles.load("agenda") == rig.profile
    assert rig.target.requests == []
    (folder / "openapi.json").write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(ConfigError):
        profiles.load("agenda")


def test_captura_recusa_sem_aprovacao(tmp_path: Path) -> None:
    capture, rig = _setup(tmp_path, approved=False)
    with pytest.raises(ScopeNotApproved):
        capture.execute("agenda")
    assert not (tmp_path / "agenda" / "knowledge.captured.yml").exists()
    assert rig.target.requests == []


def test_conhecimento_ativo_recusa_motor_ausente(tmp_path: Path) -> None:
    capture, rig = _setup(tmp_path)
    capture.execute("agenda")
    folder = tmp_path / "agenda"
    _validate_captured(folder)
    (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")
    profiles = KnowledgeProfiles(
        rig.profiles,
        FileKnowledgeStore(tmp_path),
        FileStrategyRepository(tmp_path),
        rig.clock,
        None,
    )
    with pytest.raises(ConfigError, match="motor atual"):
        profiles.load("agenda")


def test_captura_sem_run_emite_somente_propostas_sem_origem_do_dono(tmp_path: Path) -> None:
    import yaml

    capture, _ = _setup(tmp_path)
    capture.execute("agenda")
    data = yaml.safe_load(
        (tmp_path / "agenda" / "knowledge.captured.yml").read_text(encoding="utf-8")
    )
    assert {entry["state"] for entry in data["entries"]} == {"proposed"}
    assert "owner" not in {entry["source"] for entry in data["entries"]}


def test_conhecimento_apenas_proposto_e_ignorado_sem_motor(tmp_path: Path) -> None:
    capture, rig = _setup(tmp_path)
    capture.execute("agenda")
    folder = tmp_path / "agenda"
    (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")
    profiles = KnowledgeProfiles(
        rig.profiles,
        FileKnowledgeStore(tmp_path),
        FileStrategyRepository(tmp_path),
        rig.clock,
        None,
    )
    assert profiles.load("agenda") == rig.profile


def test_probe_recusa_fonte_alterada_entre_validacao_e_leitura(tmp_path: Path) -> None:
    from harness_dast.adapters.datagen import GeneratorCatalogue
    from harness_dast.application.probe import Probe, ProbeRequest
    from harness_dast.domain.datagen import DataRules
    from harness_dast.domain.flow import FlowSpec
    from harness_dast.domain.probe_result import ArtifactHashes
    from harness_dast.domain.profile import ProductProfile

    capture, rig = _setup(tmp_path)
    capture.execute("agenda")
    folder = tmp_path / "agenda"
    _validate_captured(folder)
    (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")

    class ChangedDocuments:
        def load_data_rules(self, product: str) -> DataRules | None:
            return rig.documents.load_data_rules(product)

        def load_flows(self, product: str) -> FlowSpec | None:
            (folder / "openapi.json").write_text('{"changed": true}', encoding="utf-8")
            return rig.documents.load_flows(product)

        def hashes(self, product: str, profile: ProductProfile) -> ArtifactHashes:
            return rig.documents.hashes(product, profile)

    profiles = KnowledgeProfiles(
        rig.profiles,
        FileKnowledgeStore(tmp_path),
        FileStrategyRepository(tmp_path),
        rig.clock,
        rig.zap,
    )
    probe = Probe(
        profiles=profiles,
        specs=InMemorySpecs(rig.spec),
        documents=ChangedDocuments(),
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
    )
    with pytest.raises(ConfigError):
        probe.execute(ProbeRequest(product="agenda"))
    assert rig.target.requests == []


def test_cleanup_ignora_conhecimento_mesmo_validado_e_sem_motor(tmp_path: Path) -> None:
    from harness_dast.cli.approval_composition import checked_profiles
    from tests.fakes.approvals import approve_product_on_disk
    from tests.fakes.profile_data import dump_yaml, valid_profile_data

    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "target.yml").write_text(dump_yaml(valid_profile_data()), encoding="utf-8")
    (folder / "knowledge.yml").write_text("não é um conhecimento válido: [", encoding="utf-8")
    approve_product_on_disk(tmp_path, "demo")

    profile = checked_profiles(tmp_path, with_knowledge=False).load("demo")

    assert profile.product == "demo"
    with pytest.raises(ConfigError):
        checked_profiles(tmp_path).load("demo")
