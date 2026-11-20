"""Prova local e testes de conversão das medidas do processo da CLI."""

import importlib
import sys
from types import SimpleNamespace

import pytest

from harness_dast.adapters import scan_process


def test_amostra_do_processo_atual_e_nao_negativa() -> None:
    cpu, memory = scan_process.SystemProcessSampler().sample()
    assert cpu >= 0
    if memory is not None:
        assert memory > 0


@pytest.mark.skipif(sys.platform != "win32", reason="prova da API do processo Windows")
def test_windows_retorna_pico_real_de_memoria() -> None:
    _, memory = scan_process.SystemProcessSampler().sample()
    assert memory is not None
    assert memory > 0


@pytest.mark.parametrize(("platform", "expected"), [("linux", 4096), ("darwin", 4)])
def test_unidade_do_recurso_muda_por_plataforma(
    monkeypatch: pytest.MonkeyPatch, platform: str, expected: int
) -> None:
    resource = SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda _: SimpleNamespace(ru_maxrss=4))
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(importlib, "import_module", lambda _: resource)
    assert scan_process._peak_memory() == expected


def test_recurso_indisponivel_nao_e_convertido_em_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(_: str) -> None:
        raise ImportError("resource ausente")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(importlib, "import_module", unavailable)
    assert scan_process._peak_memory() is None
