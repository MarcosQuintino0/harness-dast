"""Trava global: nenhum teste pode abrir o cofre de credenciais REAL da máquina (ADR 0030)."""

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
