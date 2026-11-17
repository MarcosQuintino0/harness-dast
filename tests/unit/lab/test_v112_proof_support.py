"""Verifica o recorte e a sanitizaÃ§Ã£o usados pelas provas V1.12."""

import json
from pathlib import Path

import pytest

from evals.runner.metrics import measure_agent
from tests.integration.lab_support import CliResult
from tests.integration.test_crapi_focus_dryrun import _transcript
from tests.integration.v112_proof_support import control_spec, summary


def test_control_spec_recusa_operacao_incorreta(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"paths": {"/workshop/api/shop/products": {"get": {"operationId": "outro"}}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="controle inesperada"):
        control_spec(source, tmp_path / "out.json")


def test_summary_omite_mensagens_e_conteudo_externo() -> None:
    result = CliResult(0, {}, "", "")
    result.envelope.update(
        {
            "data": {
                "status": "failed",
                "stages": [
                    {
                        "name": "probe",
                        "status": "failed",
                        "message": "segredo-sintetico",
                        "duration_seconds": 2,
                    }
                ],
            }
        }
    )
    assert "segredo-sintetico" not in json.dumps(summary(result))


def test_transcript_de_ensaio_mede_tempo_sem_modelo_ou_tokens(tmp_path: Path) -> None:
    records = {
        "probe": {
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:05+00:00",
            "exit_code": 0,
        }
    }
    _transcript(tmp_path, records)
    metrics = measure_agent(tmp_path, "ensaio-sem-agente")
    assert metrics.totals.duration_seconds == 5
    assert metrics.totals.tokens is None
    assert metrics.model is None
