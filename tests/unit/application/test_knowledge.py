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


def test_captura_e_reuso_validam_fontes_sem_pedido(tmp_path: Path) -> None:
    capture, rig = _setup(tmp_path)
    result = capture.execute("agenda")
    folder = tmp_path / "agenda"
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
    (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")
    profiles = KnowledgeProfiles(
        rig.profiles,
        FileKnowledgeStore(tmp_path),
        FileStrategyRepository(tmp_path),
        rig.clock,
        None,
    )
    with pytest.raises(ConfigError):
        profiles.load("agenda")


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
