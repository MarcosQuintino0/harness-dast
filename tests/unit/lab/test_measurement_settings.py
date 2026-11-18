"""Configuração de métricas e orçamento das provas de laboratório, sem subir pilha."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.integration import test_scan_performance_matrix as matrix
from tests.integration.conftest import measurement_settings
from tests.integration.run_support import record_metrics
from tests.integration.test_lab_finding_verification import _settings as v111_settings


def test_metricas_sao_gravadas_quando_diretorio_nao_e_definido(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = measurement_settings(tmp_path_factory)["HDAST_IT_METRICS_DIR"]
    assert target is not None
    monkeypatch.setenv("HDAST_IT_METRICS_DIR", target)

    record_metrics("cenario", {"total": 1})

    assert (Path(target) / "cenario.json").is_file()


def test_metricas_preservam_diretorio_explicito(
    tmp_path_factory: pytest.TempPathFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HDAST_IT_METRICS_DIR", str(tmp_path))

    assert measurement_settings(tmp_path_factory)["HDAST_IT_METRICS_DIR"] == str(tmp_path)


@pytest.mark.parametrize("missing", ["V111_LAB_ROOT", "V111_LOCK_TOKEN"])
def test_pasta_temporaria_preserva_skip_da_v111_quando_configuracao_falta(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for name in ("V111_LAB_ROOT", "V111_LOCK_TOKEN"):
        if name != missing:
            monkeypatch.setenv(name, "teste")
    monkeypatch.delenv(missing, raising=False)
    target = measurement_settings(tmp_path_factory)["HDAST_IT_METRICS_DIR"]
    assert target is not None
    monkeypatch.setenv("HDAST_IT_METRICS_DIR", target)

    with pytest.raises(pytest.skip.Exception, match=missing):
        v111_settings()


def test_medicao_v17_pula_quando_nao_ha_orcamento() -> None:
    assert "HDAST_V17_DEADLINE_EPOCH" not in os.environ

    with pytest.raises(pytest.skip.Exception, match="HDAST_V17_DEADLINE_EPOCH"):
        matrix._remaining(30)


@pytest.mark.parametrize(("deadline", "expected"), [("120", 20), ("200", 30)])
def test_medicao_v17_limitada_pelo_tempo_restante_e_pelo_teto(
    monkeypatch: pytest.MonkeyPatch, deadline: str, expected: int
) -> None:
    monkeypatch.setenv("HDAST_V17_DEADLINE_EPOCH", deadline)
    monkeypatch.setattr(matrix, "time", SimpleNamespace(time=lambda: 100))

    assert matrix._remaining(30) == expected
