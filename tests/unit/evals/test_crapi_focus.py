"""Contratos do caso curto e da fronteira da cópia cega."""

import json
from pathlib import Path

import pytest
import yaml

from evals.runner.approve import approve
from evals.runner.cases import REPO_ROOT, EvalError, RoundDirs, load_case
from evals.runner.prepare import prepare
from harness_dast.cli import composition
from harness_dast.cli.app import build_app, run_app
from tests.fakes.clock import FixedClock, utc


@pytest.fixture
def focus_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RoundDirs:
    monkeypatch.setattr(composition, "SystemClock", lambda: FixedClock(utc(2026, 11, 17)))
    out = tmp_path / "round"
    result = prepare("crapi-foco", "vulnerable", 7, out)
    assert not result.leaks
    return RoundDirs(out)


def _init(dirs: RoundDirs) -> Path:
    code = run_app(
        build_app(),
        [
            "--json",
            "init",
            "crapi",
            "--from-letter",
            str(dirs.workspace / "inputs/carta.yml"),
            "--products-dir",
            str(dirs.workspace / "products"),
        ],
    )
    assert code == 0
    return dirs.workspace / "products/crapi/target.yml"


def test_prepara_copia_sem_gabarito_quando_caso_foco(focus_round: RoundDirs) -> None:
    ws = focus_round.workspace
    assert (ws / "inputs/carta.yml").read_bytes() == (
        REPO_ROOT / "evals/cases/crapi-foco/carta.yml"
    ).read_bytes()
    assert (ws / "inputs/openapi.json").is_file()
    assert not (ws / "evals").exists()
    assert not (ws / "docs/adr").exists()
    assert not (ws / "lab/crapi/README.md").exists()
    assert not (ws / "lab/crapi/seed.py").exists()
    skills = {p.name for p in (ws / ".claude/skills").iterdir() if p.is_dir()}
    assert skills == {
        "onboard-product",
        "fix-reachability",
        "run-scan",
        "triage-findings",
        "test-product",
    }
    manifest = json.loads(
        (focus_round.sealed / "workspace-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["policy"] == "allowlist-v1"
    assert manifest["stage"] == "repository-copy"
    assert manifest["total_files"] == sum(manifest["roots"].values())


def test_ensaio_aprova_perfil_gerado_pela_carta(focus_round: RoundDirs) -> None:
    profile = _init(focus_round)
    data = yaml.safe_load(profile.read_text(encoding="utf-8"))
    assert data["scan"]["strength"] == "LOW"
    assert approve(focus_round.out).product == "crapi"


def test_ensaio_recusa_perfil_com_escopo_alargado(focus_round: RoundDirs) -> None:
    profile = _init(focus_round)
    data = yaml.safe_load(profile.read_text(encoding="utf-8"))
    data["scope"]["allow"][0]["paths"].append("/identity/api/**")
    profile.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(EvalError, match="alarga"):
        approve(focus_round.out)
    assert not (focus_round.state / "approvals").exists()


def test_caso_nao_declara_detecao_ou_prazo_medido() -> None:
    case = load_case("crapi-foco")
    assert {f.id for f in case.flaws} == {"C1", "C6", "C10", "C11", "C12", "C15"}
    assert not any(f.detectable for f in case.flaws)
    assert case.budget.duration_seconds == 900
