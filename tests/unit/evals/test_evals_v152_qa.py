"""Regressões independentes da régua e do lacre da rodada."""

import copy
import json
import shutil
from pathlib import Path

import pytest

from evals.runner.cases import RoundDirs, load_case, load_round_case
from evals.runner.checks_findings import read_findings
from evals.runner.checks_profile import profile_checks
from evals.runner.prepare import prepare
from evals.runner.scoring import Cost, compute
from tests.unit.evals.support import CASES, GOOD_PROFILE, write_json


@pytest.mark.parametrize("value", [None, "not_found", ["not_found", "unknown"], [True], {}])
def test_outcomes_malformados_ou_nao_autorizados_sao_recusados(value: object) -> None:
    profile = copy.deepcopy(GOOD_PROFILE)
    profile["scan"] = {"include_outcomes": value}
    checks = profile_checks(profile, load_case("clinica-piloto"))
    assert not next(c for c in checks if c.id == "attack_permissions").passed


def test_rodada_usa_caso_lacrado_apos_alteracao_da_fonte(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    cases = tmp_path / "cases"
    shutil.copytree(CASES, cases)
    original = load_case("mini", cases)
    prepare("mini", "vulnerable", 7, out, source=repo, cases_dir=cases)
    (cases / "mini" / "case.yml").write_text("não é um caso válido", encoding="utf-8")

    assert load_round_case(RoundDirs(out), "mini", cases) == original


def test_fontes_desconhecidas_nao_entram_e_fingerprints_repetidos_sao_unicos(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "trace"
    repeated = {"fingerprint": "same", "title": "repetido"}
    write_json(
        trace / "runs/a/findings.json",
        {
            "findings": [repeated],
            "proxy_signals": {"findings": [{"fingerprint": "signal", "category": "sql_error"}]},
            "unknown_source": {"findings": [{"fingerprint": "unknown"}]},
        },
    )
    write_json(trace / "runs/b/findings.json", {"findings": [repeated]})

    assert {item["fingerprint"] for item in read_findings(trace)} == {"same", "signal"}


def test_nota_antiga_sem_snapshot_preserva_nota_arquivada(tmp_path: Path) -> None:
    archive = Path("evals/results/2026-11-14-clinica-piloto-terra61-medium-wide/attempts/02-main")
    out = tmp_path / "round"
    shutil.copytree(archive / "trace", out / "trace")
    shutil.move(out / "trace/executions", out / "trace/runs")
    shutil.copy2(archive / "transcript.jsonl", out / "transcript.jsonl")
    for file in (out / "trace").rglob("*.md.txt"):
        shutil.copy2(file, file.with_suffix(""))
    (out / "sealed").mkdir()
    (out / "sealed/mode.json").write_text(
        '{"case":"clinica-piloto","mode":"vulnerable"}', encoding="utf-8"
    )

    result = compute(out, Cost(tokens=8023944, duration_seconds=1777))
    saved = json.loads((archive / "score.json").read_text(encoding="utf-8"))
    assert result["grade"] == saved["grade"]
