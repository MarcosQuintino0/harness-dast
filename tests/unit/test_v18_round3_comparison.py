"""Garante que lacunas nas comparações T4 não se tornem igualdade comprovada."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any


def _module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "evals/measurements/v1-8/round3/compare_round3.py"
    spec = importlib.util.spec_from_file_location("round3_compare", path)
    assert spec is not None
    assert spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def _record() -> dict[str, Any]:
    return {
        "manifest": {"run_id": "r"},
        "exit_code": 0,
        "scan": {
            "status": "completed",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:01Z",
            "entries": [{"operation_id": "one"}],
        },
        "rule_stats": {
            "operations": [
                {
                    "operation_id": "one",
                    "rules": [
                        {
                            "plugin_id": 40026,
                            "state": "skipped",
                            "skip_reason": "other",
                            "requests": 0,
                        },
                        {"plugin_id": 6, "state": "completed", "requests": None, "alerts": 0},
                    ],
                }
            ]
        },
    }


def test_valores_ausentes_nao_comprovam_igualdade(tmp_path: Path) -> None:
    record = _record()
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(record), encoding="utf-8")
    b.write_text(json.dumps(record), encoding="utf-8")
    result = _module().compare(a, b)
    assert result["diagnostics"]["context_equal"]["policy"] is None
    assert result["diagnostics"]["context_equal"]["probe"] is None
    assert result["diagnostics"]["a"]["missing_rule_counts"] == [
        {"operation_id": "one", "plugin_id": 6, "field": "requests"}
    ]
    assert result["diagnostics"]["a"]["account_event_counts"] is None


def test_exclusao_dom_exige_registro_para_cada_operacao(tmp_path: Path) -> None:
    record = _record()
    record["rule_stats"]["operations"].append({"operation_id": "two", "rules": []})
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(record), encoding="utf-8")
    b.write_text(json.dumps(record), encoding="utf-8")
    result = _module().compare(a, b)
    assert not result["dom_40026"]["historical_exclusion_valid"]


def test_campo_aninhado_ausente_nao_vira_igualdade(tmp_path: Path) -> None:
    record = _record()
    record["scan"]["policy"] = {"name": "hdast", "strength": None}
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(record), encoding="utf-8")
    b.write_text(json.dumps(record), encoding="utf-8")
    result = _module().compare(a, b)
    assert result["diagnostics"]["context_equal"]["policy"] is None
