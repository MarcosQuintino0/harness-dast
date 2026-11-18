"""Confere o mapa com os marcadores coletados pelo pytest, sem executar a integração."""

import subprocess
import sys
from pathlib import PurePosixPath
from typing import Literal

import pytest

from tests.integration.lab_round import INTEGRATION, MAP, ROOT, load_map, render_area_table

pytestmark = pytest.mark.contract


@pytest.mark.parametrize("level", ["fast", "prova"])
def test_mapa_cobre_todos_os_arquivos_coletados(level: Literal["fast", "prova"]) -> None:
    mapped = set(load_map(MAP).files(level))
    result = subprocess.run(  # noqa: S603 - apenas coleta, sem shell.
        (sys.executable, "-m", "pytest", INTEGRATION, "-m", f"lab_{level}", "--collect-only", "-q"),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stdout
    collected = {
        PurePosixPath(line.partition("::")[0].replace("\\", "/")).name
        for line in result.stdout.splitlines()
        if "::" in line and line.partition("::")[0].endswith(".py")
    }
    # A igualdade também detecta arquivos removidos ou marcados no nível errado.
    assert collected == mapped


def test_tabela_da_escada_reflete_o_mapa() -> None:
    document = ROOT / "docs/desenvolver/escada-de-testes.md"

    assert render_area_table(load_map(MAP)) in document.read_text(encoding="utf-8")
