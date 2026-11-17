"""A régua privada e sua decisão não atravessam a cópia cega."""

from pathlib import Path

from evals.runner.cases import load_case
from evals.runner.prepare import copy_workspace
from tests.unit.evals.test_workspace_boundary import ROOT


def test_copia_real_omite_regua_gabarito_e_adr_privado(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    copy_workspace(load_case("vampi"), ROOT, workspace)

    assert not (workspace / "evals").exists()
    assert not (workspace / "docs/adr/0089-criterio-privado-triagem.md").exists()
    assert (workspace / ".claude/skills/triage-findings/SKILL.md").is_file()


def test_regua_separa_resultados_e_preserva_nota_historica() -> None:
    rubric = (ROOT / "evals/rubrics/triage-accuracy-v1.md").read_text(encoding="utf-8")

    for category in ("Acertou", "Errou", "Indeterminado", "Não avaliado"):
        assert category in rubric
    assert "nota automática histórica" in rubric
    assert "modo seguro" in rubric
    assert "gabarito" in rubric
