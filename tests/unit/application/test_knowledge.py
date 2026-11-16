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
