"""Critérios conservadores da previsão de desempenho V1.7."""

import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[3] / "evals" / "measurements" / "v1.7" / "analyze.py"
SPEC = importlib.util.spec_from_file_location("v17_analyze", PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_previsao_pondera_regra_sem_tratar_soma_como_parede() -> None:
    data = {
        "wall_a": 100,
        "expected_rule_ids": ["x", "y"],
        "rules": {
            "x": {"full_a": 30, "t3_a": [10, 10, 10], "t3_b": [5, 5, 5], "complete": True},
            "y": {"full_a": 70, "t3_a": [10, 10, 10], "t3_b": [10, 10, 10], "complete": True},
        },
    }
    result = MODULE.predict(data)
    assert result["wall_b"] == 85
    assert result["gain_pct"] == 15


def test_previsao_inconclusiva_quando_regra_nao_foi_amostrada() -> None:
    data = {"wall_a": 100, "expected_rule_ids": ["x", "y"], "rules": {"x": {}}}
    assert MODULE.predict(data)["status"] == "inconclusivo"


def test_previsao_inconclusiva_quando_tempo_e_zero() -> None:
    data = {
        "wall_a": 100,
        "expected_rule_ids": ["x"],
        "rules": {"x": {"full_a": 3, "t3_a": [1, 0, 1], "t3_b": [1, 1, 1], "complete": True}},
    }
    assert MODULE.predict(data)["status"] == "inconclusivo"
