"""Prova do isolamento: uma pilha "no ar" na pasta padrão da máquina não chega aos testes."""

import os
from pathlib import Path

import pytest

from harness_dast.adapters.storage.stack_state import STATE_FILE_NAME
from harness_dast.application.stack_models import ComposeProject, StackState
from harness_dast.cli.stack_composition import load_effective_settings, open_state_store

pytestmark = pytest.mark.contract

REAL_STACK_KEY = "chave-da-pilha-real-no-ar"


def _running_stack(base: Path) -> StackState:
    return StackState(
        product="demo",
        run_id="real-run",
        started_at="2026-11-14T10:00:00Z",
        not_after="2026-11-14T12:00:00Z",
        zap_api_key=REAL_STACK_KEY,
        zap_url="http://127.0.0.1:18080",
        auth_proxy_url="http://127.0.0.1:18081",
        policy_dir=base / "policy",
        audit_dir=base / "audit",
        projects=(ComposeProject(name="hdast", workdir=str(base), files=("compose.yml",)),),
    )


def _write_state(folder: Path) -> None:
    folder.mkdir(parents=True)
    (folder / STATE_FILE_NAME).write_text(
        _running_stack(folder).model_dump_json(), encoding="utf-8"
    )


def test_running_stack_in_the_default_folders_is_invisible_to_tests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Simula a máquina com a pilha no ar nas pastas padrão (Windows e POSIX).
    machine = tmp_path / "machine"
    _write_state(machine / "local-app-data" / "hdast")
    _write_state(machine / "xdg-state" / "hdast")
    _write_state(machine / "home" / ".local" / "state" / "hdast")
    monkeypatch.setenv("LOCALAPPDATA", str(machine / "local-app-data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(machine / "xdg-state"))
    monkeypatch.setenv("HOME", str(machine / "home"))
    monkeypatch.setenv("USERPROFILE", str(machine / "home"))

    state = open_state_store().load()
    settings = load_effective_settings()
    # Controle: sem a fixture de isolamento, a mesma simulação enxergaria a pilha.
    monkeypatch.delenv("HDAST_STATE_DIR")
    visible = open_state_store().load()

    assert visible is not None
    assert state is None
    assert settings.zap_api_key is None


def test_hdast_variables_of_the_real_environment_do_not_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A fixture autouse já limpou o ambiente: nenhuma HDAST_* além da pasta de estado isolada.
    leaked = sorted(name for name in os.environ if name.startswith("HDAST_"))

    assert leaked == ["HDAST_STATE_DIR"]
