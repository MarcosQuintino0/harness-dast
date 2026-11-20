"""Captura de vínculo local sem acesso ao alvo."""

from pathlib import Path

import pytest

from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.application.strategy_capture import CaptureStrategy
from harness_dast.domain.errors import ConfigError, ScopeNotApproved
from harness_dast.domain.strategy import Strategy
from tests.fakes.approvals import InMemoryApprovalStore, approval_for
from tests.fakes.probe_ports import InMemorySpecs
from tests.fakes.rig import Rig


def _capture(tmp_path: Path, *, approved: bool = True) -> tuple[CaptureStrategy, Rig]:
    rig = Rig()
    directory = tmp_path / "agenda"
    directory.mkdir()
    (directory / "openapi.json").write_text("{}", encoding="utf-8")
    approvals = InMemoryApprovalStore()
    if approved:
        approvals.write(approval_for(rig.profile))
    capture = CaptureStrategy(
        rig.profiles,
        FileStrategyRepository(tmp_path),
        approvals,
        rig.clock,
        rig.documents,
        InMemorySpecs(rig.spec),
        rig.zap,
        "http://127.0.0.1:8080",
    )
    return capture, rig


def test_capture_cria_copia_vinculada_sem_tocar_alvo(tmp_path: Path) -> None:
    capture, rig = _capture(tmp_path)

    result = capture.execute("agenda", "strategy.captured.yml")

    directory = tmp_path / "agenda"
    assert result["activated"] is False
    assert not (directory / "strategy.yml").exists()
    assert rig.target.requests == []
    (directory / "strategy.captured.yml").rename(directory / "strategy.yml")
    saved = Strategy.from_data(FileStrategyRepository(tmp_path).read("agenda"))
    assert saved.choices[0].basis is not None
    assert saved.choices[0].source == "observation"


def test_capture_recusa_sem_aprovacao_e_nao_cria_copia(tmp_path: Path) -> None:
    capture, rig = _capture(tmp_path, approved=False)

    with pytest.raises(ScopeNotApproved):
        capture.execute("agenda", "strategy.captured.yml")

    assert not (tmp_path / "agenda" / "strategy.captured.yml").exists()
    assert rig.target.requests == []


def test_capture_nao_sobrescreve_destino_existente(tmp_path: Path) -> None:
    capture, _ = _capture(tmp_path)
    destination = tmp_path / "agenda" / "strategy.captured.yml"
    destination.write_text("original", encoding="utf-8")

    with pytest.raises(ConfigError):
        capture.execute("agenda", destination.name)

    assert destination.read_text(encoding="utf-8") == "original"
