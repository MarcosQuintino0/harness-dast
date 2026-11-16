"""O ritmo da avaliação altera só a cópia e acompanha a medição."""

import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from evals.runner.cases import EvalError
from evals.runner.cli import build_parser
from evals.runner.measurements import save_measurement, write_agent_metrics
from evals.runner.metrics import measure_agent
from evals.runner.pacing import configure_pacing, read_pacing
from evals.runner.prepare import prepare
from tests.unit.evals.support import CASES, write
from tests.unit.evals.test_metrics import standard_round


@pytest.mark.parametrize("pacing", ["legacy", "proxy"])
def test_prepare_quando_ritmo_escolhido_muda_so_modelo_copiado_e_registra_meta(
    repo: Path,
    out: Path,
    tmp_path: Path,
    pacing: str,
) -> None:
    template = repo / "products/_template/target.yml"
    before = "schema_version: 1\n# modelo original\nscan:\n  strength: medium\n"
    template.write_text(before, encoding="utf-8")
    result = prepare("mini", "vulnerable", 7, out, source=repo, cases_dir=CASES, pacing=pacing)
    copied = (result.workspace / "products/_template/target.yml").read_text(encoding="utf-8")
    assert template.read_text(encoding="utf-8") == before
    if pacing == "legacy":
        assert copied == before
    else:
        assert yaml.safe_load(copied)["scan"] == {"strength": "medium", "pacing": "proxy"}
    assert read_pacing(out) == pacing
    standard_round().save(out)
    metrics = measure_agent(out)
    assert metrics.pacing == pacing
    written = write_agent_metrics(out, metrics)
    assert json.loads(written.read_text(encoding="utf-8"))["pacing"] == pacing
    folder = save_measurement(out, metrics, "pacing", date(2026, 11, 16), tmp_path / "measurements")
    assert json.loads((folder / "meta.json").read_text(encoding="utf-8"))["pacing"] == pacing


def test_parser_quando_pacing_omitido_ou_invalido() -> None:
    args = build_parser().parse_args(["prepare", "--case", "mini", "--out", "round"])
    assert args.pacing == "legacy"
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["prepare", "--case", "mini", "--out", "round", "--pacing", "fast"]
        )


def test_recusa_ritmo_invalido_quando_chamada_direta(tmp_path: Path) -> None:
    with pytest.raises(EvalError, match="Ritmo inválido"):
        configure_pacing(tmp_path, "fast")


@pytest.mark.parametrize("content", ["[", "[]", "scan: []"])
def test_recusa_quando_modelo_nao_e_yaml_com_scan_mapa(tmp_path: Path, content: str) -> None:
    write(tmp_path / "products/_template/target.yml", content)
    with pytest.raises(EvalError):
        configure_pacing(tmp_path, "proxy")


def test_recusa_quando_modelo_ausente(tmp_path: Path) -> None:
    with pytest.raises(EvalError):
        configure_pacing(tmp_path, "proxy")


@pytest.mark.parametrize(
    "content", ["{", "{}", '{"pacing":"fast"}', '{"pacing":"proxy","schema_version":2}']
)
def test_recusa_meta_quando_ausente_malformado_ou_invalido(tmp_path: Path, content: str) -> None:
    write(tmp_path / "meta.json", content)
    with pytest.raises(EvalError):
        read_pacing(tmp_path)


def test_ritmo_desconhecido_quando_rodada_historica_sem_meta(tmp_path: Path) -> None:
    assert read_pacing(tmp_path) is None
