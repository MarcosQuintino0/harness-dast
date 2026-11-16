"""Resumo e previsão prévia não confundem dados ausentes com resultados válidos."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.integration.v17_matrix import PILOT, VAMPI

PATH = Path(__file__).resolve().parents[3] / "evals" / "measurements" / "v1.7" / "summarize.py"
SPEC = importlib.util.spec_from_file_location("v17_summarize", PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(PATH.parent))
try:
    SPEC.loader.exec_module(MODULE)
finally:
    sys.path.remove(str(PATH.parent))


def _record(layer: str, variant: str, product: str = "vampi") -> dict[str, Any]:
    operations = VAMPI if product == "vampi" else PILOT
    entries = [
        {"operation_id": op, "outcome": "completed", "truncated": False, "scan_id": str(index)}
        for index, op in enumerate(operations)
    ]
    rules = [
        {"operation_id": op, "rules": [{"plugin_id": 6, "state": "completed", "time_ms": 100}]}
        for op in operations
    ]
    return {
        "product": product,
        "mode": "vulnerable",
        "variant": variant,
        "layer": layer,
        "scan": {
            "status": "completed",
            "started_at": "2026-11-16T10:00:00+00:00",
            "finished_at": "2026-11-16T10:01:00+00:00",
            "entries": entries,
            "planned": [{"operation_id": op} for op in operations],
            "skipped": [],
            "policy": {"strength": "HIGH"},
            "limits": {"delay_ms": 20 if variant == "A" else 0, "threads_per_host": 8},
        },
        "rule_stats": {"operations": rules},
        "zap_config_sampling": {
            "status": "observed",
            "samples": [
                {
                    "at": "2026-11-16T10:00:30+00:00",
                    "delay_ms": 20 if variant == "A" else 0,
                    "scans": [{"id": "0", "state": "RUNNING", "progress": 42}],
                }
            ],
        },
        "profile": {
            "scope": {"allow": ["lab"]},
            "limits": {"requests_per_second": 50},
            "scan": {"pacing": "legacy" if variant == "A" else "proxy"},
        },
        "accounts": [
            {
                "phase": "decision",
                "decision": "allowed",
                "operation_id": "x",
                "account": "user_a",
                "method": "GET",
                "route": "zap",
            }
        ],
    }


def _write(folder: Path, layer: str, index: int, variant: str, data: dict[str, Any]) -> None:
    path = folder / f"v17-{layer}-{data['product']}-vulnerable-{index}-{variant}.json"
    path.write_text(json.dumps(data), encoding="utf-8")


def _complete(folder: Path) -> None:
    for index in (1, 2, 3):
        for variant in ("A", "B"):
            _write(folder, "t3", index, variant, _record("t3", variant))
    _write(folder, "t4", 1, "A", _record("t4", "A"))


def test_pares_completos_produzem_previsao_sem_aceitar_qualidade(tmp_path: Path) -> None:
    _complete(tmp_path)
    summary, predictions = MODULE.summarize(tmp_path)
    assert summary["quality_accepted"] is False
    assert summary["groups"]["vampi/vulnerable"]["median_pct_descriptive"] == 0
    assert predictions["vampi/vulnerable"]["input"]["expected_rule_ids"] == ["6"]
    assert predictions["vampi/vulnerable"]["result"]["status"] == "previsão"
    assert len(predictions["vampi/vulnerable"]["sha256"]) == 64


def test_truncamento_ou_regra_ausente_nao_gera_previsao(tmp_path: Path) -> None:
    _complete(tmp_path)
    record = _record("t3", "B")
    record["scan"]["entries"][0]["truncated"] = True
    _write(tmp_path, "t3", 2, "B", record)
    summary, predictions = MODULE.summarize(tmp_path)
    assert predictions == {}
    assert summary["quality_accepted"] is False


def test_operacao_planejada_sem_resultado_nao_gera_previsao(tmp_path: Path) -> None:
    _complete(tmp_path)
    record = _record("t4", "A")
    record["scan"]["planned"].append({"operation_id": "nao_executada"})
    _write(tmp_path, "t4", 1, "A", record)
    assert MODULE.summarize(tmp_path)[1] == {}


def test_regra_sem_tempo_nao_gera_previsao(tmp_path: Path) -> None:
    _complete(tmp_path)
    record = _record("t3", "A")
    record["rule_stats"]["operations"][0]["rules"][0]["time_ms"] = None
    _write(tmp_path, "t3", 1, "A", record)
    assert MODULE.summarize(tmp_path)[1] == {}


def test_nao_congela_previsao_apos_observar_t4_b(tmp_path: Path) -> None:
    _complete(tmp_path)
    _write(tmp_path, "t4", 1, "B", _record("t4", "B"))
    assert MODULE.summarize(tmp_path)[1] == {}


def test_confirma_com_hash_previo_mas_mantem_qualidade_inconclusiva(tmp_path: Path) -> None:
    _complete(tmp_path)
    frozen = MODULE.summarize(tmp_path)[1]
    _write(tmp_path, "t4", 1, "B", _record("t4", "B"))
    summary, _ = MODULE.summarize(tmp_path, frozen)
    result = summary["groups"]["vampi/vulnerable"]["t4_confirmation"]
    assert result["difference_pp"] == pytest.approx(0)
    assert result["status"].startswith("inconclusivo")


def test_rejeita_hash_alterado_na_confirmacao(tmp_path: Path) -> None:
    _complete(tmp_path)
    frozen = MODULE.summarize(tmp_path)[1]
    frozen["vampi/vulnerable"]["result"]["gain_pct"] = 99
    _write(tmp_path, "t4", 1, "B", _record("t4", "B"))
    summary, _ = MODULE.summarize(tmp_path, frozen)
    assert "hash" in summary["groups"]["vampi/vulnerable"]["t4_confirmation"]["reason"]


def test_uma_previsao_nova_nao_substitui_mapa_congelado_da_outra_api(tmp_path: Path) -> None:
    _complete(tmp_path)
    prior = MODULE.summarize(tmp_path)[1]
    _write(tmp_path, "t4", 1, "B", _record("t4", "B"))
    for index in (1, 2, 3):
        for variant in ("A", "B"):
            _write(tmp_path, "t3", index, variant, _record("t3", variant, "clinica-piloto"))
    _write(tmp_path, "t4", 1, "A", _record("t4", "A", "clinica-piloto"))
    summary, predictions = MODULE.summarize(tmp_path, prior)
    assert "clinica-piloto/vulnerable" in predictions
    assert summary["groups"]["vampi/vulnerable"]["t4_confirmation"][
        "difference_pp"
    ] == pytest.approx(0)


@pytest.mark.parametrize("delay", [None, -1, 20, "0", True])
def test_sem_ritmo_b_comprovado_nao_congela_previsao(tmp_path: Path, delay: object) -> None:
    _complete(tmp_path)
    record = _record("t3", "B")
    record["scan"]["limits"]["delay_ms"] = delay
    _write(tmp_path, "t3", 2, "B", record)
    assert MODULE.summarize(tmp_path)[1] == {}


@pytest.mark.parametrize(
    "case", ["ausente", "divergente", "outro_scan", "fora_janela", "concluido"]
)
def test_leitura_indisponivel_ou_invalidada_nao_confirma_ritmo(tmp_path: Path, case: str) -> None:
    _complete(tmp_path)
    record = _record("t3", "B")
    sampling = record["zap_config_sampling"]
    sample = sampling["samples"][0]
    if case == "ausente":
        sampling["samples"] = []
    elif case == "divergente":
        sample["delay_ms"] = 20
    elif case == "outro_scan":
        sample["scans"][0]["id"] = "999"
    elif case == "fora_janela":
        sample["at"] = "2026-11-16T09:59:59+00:00"
    else:
        sample["scans"][0]["state"] = "FINISHED"
    _write(tmp_path, "t3", 2, "B", record)
    assert MODULE.summarize(tmp_path)[1] == {}


def test_arquivo_malformado_ou_duracao_ausente_fica_inconclusivo(tmp_path: Path) -> None:
    _write(tmp_path, "t3", 1, "A", _record("t3", "A"))
    (tmp_path / "v17-t3-vampi-vulnerable-1-B.json").write_text("{", encoding="utf-8")
    summary, predictions = MODULE.summarize(tmp_path)
    assert summary["invalid"]
    assert predictions == {}
    assert MODULE.duration({}) is None


def test_cli_grava_arquivos_novos_sem_sobrescrever(tmp_path: Path) -> None:
    summary, prediction = tmp_path / "summary.json", tmp_path / "prediction.json"
    command = [
        sys.executable,
        str(PATH),
        str(tmp_path),
        "--output",
        str(summary),
        "--prediction-output",
        str(prediction),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)  # noqa: S603
    assert first.returncode == 0, first.stderr
    assert json.loads(summary.read_text(encoding="utf-8"))["status"] == "inconclusivo"
    second = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)  # noqa: S603
    assert second.returncode != 0
