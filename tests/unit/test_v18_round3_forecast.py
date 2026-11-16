"""A previsao congelada aceita somente mudanca uniforme de terminador."""

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "evals/measurements/v1-8/round3/compare_round3.py"
    spec = importlib.util.spec_from_file_location("round3_forecast_compare", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("actual", ["lf", "crlf"])
@pytest.mark.parametrize("recorded", ["lf", "crlf"])
def test_conversao_uniforme_preserva_conteudo(actual: str, recorded: str) -> None:
    variants = {"lf": b'{\n "value": 1\n}\n', "crlf": b'{\r\n "value": 1\r\n}\r\n'}
    expected = hashlib.sha256(variants[recorded]).hexdigest()
    info = _module().verify_forecast_bytes(variants[actual], expected)
    assert info["actual_variant"] == actual
    assert info["recorded_variant"] == recorded
    assert info["actual_sha256"] == hashlib.sha256(variants[actual]).hexdigest()
    assert info["recorded_sha256"] == expected


def test_alteracao_de_conteudo_e_recusada() -> None:
    expected = hashlib.sha256(b'{\r\n "value": 1\r\n}\r\n').hexdigest()
    with pytest.raises(ValueError, match="nao corresponde"):
        _module().verify_forecast_bytes(b'{\n "value": 2\n}\n', expected)


def test_terminadores_mistos_sao_recusados() -> None:
    expected = hashlib.sha256(b'{\r\n "value": 1\r\n}\r\n').hexdigest()
    with pytest.raises(ValueError, match="misturados"):
        _module().verify_forecast_bytes(b'{\r\n "value": 1\n}\r\n', expected)
