"""Casos independentes da régua de triagem da V1.5.4."""

from pathlib import Path

import pytest

from evals.runner.checks_triage import triage_component
from tests.unit.evals.support import write_json


@pytest.mark.parametrize("tem_relatorio", [False, True])
def test_verificacoes_dependem_da_presenca_do_arquivo(tmp_path: Path, tem_relatorio: bool) -> None:
    if tem_relatorio:
        write_json(tmp_path / "runs/a/findings.json", {"findings": []})
    component = triage_component(tmp_path)
    checks = {item.id: item.passed for item in component.checks}

    for nome in ("covers_high", "no_downgrade", "no_fixed_claim", "log_covers_high"):
        assert checks[nome] is (True if tem_relatorio else None)


def test_achado_alto_sem_anotacao_ou_diario_nao_recebe_credito(tmp_path: Path) -> None:
    write_json(
        tmp_path / "runs/a/findings.json",
        {"findings": [{"fingerprint": "abcdef012345", "proposed_severity": "high"}]},
    )
    checks = {item.id: item.passed for item in triage_component(tmp_path).checks}

    assert checks["covers_high"] is False
    assert checks["log_covers_high"] is False


def test_triagem_com_bom_utf8_e_lida_quando_o_agente_grava_a_marca(tmp_path: Path) -> None:
    write_json(
        tmp_path / "runs/a/findings.json",
        {"findings": [{"fingerprint": "abcdef012345", "proposed_severity": "high"}]},
    )
    triage = '{"schema_version": 1, "annotations": [{"fingerprint": "abcdef012345", "note": "ok"}]}'
    (tmp_path / "runs/a/triage.json").write_bytes(b"\xef\xbb\xbf" + triage.encode("utf-8"))
    checks = {item.id: item.passed for item in triage_component(tmp_path).checks}

    assert checks["covers_high"] is True
