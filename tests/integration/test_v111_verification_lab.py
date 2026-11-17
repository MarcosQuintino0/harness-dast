"""Portão de segurança para a futura prova operacional da V1.11.

A CLI atual fixa nomes de projetos Compose compartilhados. A prova deve falhar antes de
subir qualquer pilha até existir suporte real ao sufixo exclusivo exigido pelo operador.
"""

import json
import os
import secrets
from datetime import datetime
from pathlib import Path

import pytest

from harness_dast.application.lab_targets import PILOT_PROJECT
from harness_dast.application.stack import MAIN_PROJECT

pytestmark = pytest.mark.integration

LOCK = Path("C:/harness-dast-artefatos/lab.lock")
ARTIFACTS = Path("C:/harness-dast-artefatos/v1-11")


@pytest.fixture(scope="module")
def lab_settings() -> tuple[str | None, str | None]:
    """Captura apenas parâmetros não secretos antes do isolamento do ambiente de testes."""
    return os.environ.get("HDAST_V111_LAB_ROOT"), os.environ.get("HDAST_V111_LOCK_TOKEN")


def test_v111_lab_exige_isolamento_antes_de_operar(
    lab_settings: tuple[str | None, str | None],
) -> None:
    """Recusa a prova antes de Docker enquanto os projetos não forem exclusivos."""
    root_text, token = lab_settings
    if not root_text or not token:
        pytest.skip("Prova V1.11 exige raiz descartável e token da trava do coordenador.")
    root = Path(root_text).resolve()
    assert root != ARTIFACTS.resolve()
    assert root.is_relative_to(ARTIFACTS.resolve())
    assert not root.exists() or (root.is_dir() and not any(root.iterdir()))
    try:
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pytest.fail("Trava global ausente ou inválida; nenhum comando foi executado.")
    assert isinstance(lock, dict)
    assert lock.get("version") == "v1.11"
    assert lock.get("owner") == "codex"
    stored_token = lock.get("token")
    if not isinstance(stored_token, str) or not secrets.compare_digest(stored_token, token):
        pytest.fail("Token da trava não confere; nenhum comando foi executado.")
    created = lock.get("created_utc")
    assert isinstance(created, str)
    assert created.endswith("Z")
    datetime.fromisoformat(created.replace("Z", "+00:00"))
    assert MAIN_PROJECT.endswith("-codex"), (
        "A CLI fixa projetos Compose compartilhados; falta suporte ao sufixo -codex. "
        "Nenhum comando foi executado."
    )
    assert PILOT_PROJECT.endswith("-codex")
    pytest.fail("O fluxo de laboratório ainda não foi implementado; nenhum comando foi executado.")
