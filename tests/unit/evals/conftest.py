"""Fixtures do executor de avaliacao: um repositorio falso e uma pasta de rodada."""

from pathlib import Path

import pytest

from tests.unit.evals.support import write


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    files = {
        "README.md": "readme",
        "src/app.py": "print('x')",
        ".git/HEAD": "ref",
        ".venv/lib.py": "x",
        "runs/old/run.json": "{}",
        "evals/answer-keys/k.md": "gabarito",
        "tests/integration/t.py": "x",
        "tests/unit/evals/t.py": "x",
        "docs/arquivo/reviews/r.md": "relatorio",
        "docs/comecar/primeiro-uso.md": "x",
        "docs/ok.md": "texto livre",
        "lab/README.md": "x",
        "lab/mini/openapi.json": '{"openapi": "3.0.0"}',
        "lab/mini/compose.yaml": "services: {}",
        "lab/mini/Dockerfile": "FROM real",
        "lab/mini/secret-notes/n.md": "x",
        "products/_template/target.yml": "schema_version: 1",
        "products/real-profile/target.yml": "segredo",
        "src/__pycache__/x.pyc": "x",
    }
    for rel, content in files.items():
        write(root / rel, content)
    return root


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "round"
