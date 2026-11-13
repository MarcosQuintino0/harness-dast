"""Cria link de diretório para testes de escape de pasta, também no Windows sem privilégio."""

import os
import subprocess
from pathlib import Path

import pytest


def link_directory(link: Path, target: Path) -> None:
    """Faz `link` apontar para o diretório `target`; pula o teste se nada funcionar.

    Tenta link simbólico; no Windows, onde ele exige privilégio, usa junção (`mklink /J`),
    que o `Path.resolve` também segue.
    """
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if not _is_windows():
            pytest.skip("sem permissão para criar link simbólico neste ambiente")
        result = subprocess.run(  # noqa: S603 - comando fixo, caminhos vindos do tmp_path
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],  # noqa: S607
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("sem permissão para criar link ou junção neste ambiente")


def _is_windows() -> bool:
    # Em função para o mypy não dar o ramo da outra plataforma como inalcançável.
    return os.name == "nt"
