"""Travas globais de isolamento: nenhum teste depende do ambiente real da máquina.

- Cofre de credenciais real (ADR 0030): nenhum teste pode abri-lo.
- Variáveis `HDAST_*` e pasta de estado da pilha: uma pilha Docker do hdast no ar na máquina
  não pode mudar o resultado de teste nenhum.
"""

import os
from pathlib import Path

import pytest

from harness_dast.cli import secrets_composition


def _refuse_real_vault() -> None:
    raise AssertionError(
        "o teste tentou abrir o cofre de credenciais real; troque "
        "secrets_composition.default_backend por um backend de teste (tests/fakes)"
    )


@pytest.fixture(autouse=True)
def _never_touch_the_real_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secrets_composition, "default_backend", _refuse_real_vault)


@pytest.fixture(autouse=True)
def _isolate_hdast_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Limpa toda `HDAST_*` do ambiente real e aponta o estado da pilha para uma pasta vazia.

    O teste que precisa de um valor próprio o define depois, com `monkeypatch.setenv`.
    """
    for name in [name for name in os.environ if name.startswith("HDAST_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path / "isolated-hdast-state"))
