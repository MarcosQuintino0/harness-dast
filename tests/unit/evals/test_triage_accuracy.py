"""Contrato da medição privada da triagem."""

import json
from pathlib import Path
from typing import Any

import pytest

from evals.runner.cases import load_case
from evals.runner.triage_accuracy import measure

FP = "a" * 64
RUN = "2026-11-13T10-00-00Z-clinica-piloto-aaaa"


def write(path: Path, value: object, *, bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8-sig" if bom else "utf-8")


def report(run: str = RUN) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "fingerprint_version": 1,
        "run_id": run,
        "product": "clinica-piloto",
        "generated_at": "2026-11-13",
        "harness_version": "1",
        "coverage": {
            "operations_total": 1,
            "operations_sent": 1,
            "probe_successes": 1,
            "reachability": 1.0,
            "reachability_all": 1.0,
            "probe_status": "ok",
            "scan_status": "ok",
            "scans_run": 1,
            "limits": {
                "requests_per_second": 1.0,
                "max_duration_minutes": 1,
                "threads_per_host": 1,
                "delay_ms": 1,
                "max_scan_minutes": 1,
                "max_rule_minutes": 1,
            },
            "policy": {
                "name": "test",
                "strength": "low",
                "threshold": "low",
                "url_path_injection": False,
                "injectable_mask": 0,
                "disabled_rules": [],
            },
        },
        "summary": {"total": 1, "by_severity": {"high": 1}, "occurrences": 1},
        "findings": [
            {
                "fingerprint": FP,
                "finding_id": "F-aaaaaaaa",
                "title": "SQL Injection",
                "plugin_id": "1",
                "alert_ref": "1",
                "classification": {},
                "proposed_severity": "high",
                "proposed_confidence": "medium",
                "method": "GET",
                "path_template": "/api/pacientes/busca",
                "parameter": "nome",
                "attribution": "source_message",
                "occurrences": 1,
                "evidence": {},
            }
        ],
    }


def setup_run(
    trace: Path, run: str = RUN, level: str = "reproduced", suspect: bool = False
) -> Path:
    folder = trace / "runs" / run
    write(folder / "findings.json", report(run), bom=True)
    write(
        folder / "triage.json",
        {
            "schema_version": 1,
            "annotations": [
                {"fingerprint": FP, "suspected_false_positive": suspect, "reason": "motivo"}
            ],
        },
        bom=True,
    )
    write(
        folder / "verification.json",
        {
            "schema_version": 1,
            "product": "clinica-piloto",
            "run_id": run,
            "entries": [{"fingerprint": FP, "level": level, "reason": "motivo"}],
        },
        bom=True,
    )
    return folder


@pytest.mark.parametrize(
    ("mode", "level", "suspect", "cli", "agent"),
    [
        ("vulnerable", "reproduced", False, "acertou", "acertou"),
        ("vulnerable", "likely", False, "acertou", "acertou"),
        ("vulnerable", "likely_false_positive", True, "errou", "errou"),
        ("secure", "reproduced", False, "errou", "errou"),
        ("secure", "likely_false_positive", True, "acertou", "acertou"),
        ("vulnerable", "inconclusive", False, "indeterminado", "acertou"),
        ("vulnerable", "not_verifiable", False, "indeterminado", "acertou"),
    ],
)
def test_resultados_por_canal(
    tmp_path: Path, mode: str, level: str, suspect: bool, cli: str, agent: str
) -> None:
    setup_run(tmp_path, level=level, suspect=suspect)
    result = measure(tmp_path, load_case("clinica-piloto"), mode)
    assert [(r["cli"], r["agente"]) for r in result["observacoes"]] == [(cli, agent)]


def test_mesmo_fingerprint_em_execucoes_distintas(tmp_path: Path) -> None:
    setup_run(tmp_path)
    setup_run(tmp_path, "2026-11-13T10-00-01Z-clinica-piloto-bbbb")
    result = measure(tmp_path, load_case("clinica-piloto"), "secure")
    assert result["matriz"]["SQL Injection"]["falsos_reproduzidos"] == 2


def test_contexto_divergente_e_ausente(tmp_path: Path) -> None:
    folder = setup_run(tmp_path)
    write(
        folder / "verification.json",
        {"schema_version": 1, "product": "outro", "run_id": RUN, "entries": []},
    )
    (folder / "triage.json").unlink()
    result = measure(tmp_path, load_case("clinica-piloto"), "vulnerable")
    assert (result["observacoes"][0]["cli"], result["observacoes"][0]["agente"]) == (
        "não avaliado",
        "não avaliado",
    )
    assert len(result["problemas"]) == 2


def test_orfao_e_anotacao_sem_classificacao(tmp_path: Path) -> None:
    folder = setup_run(tmp_path)
    write(
        folder / "triage.json",
        {"schema_version": 1, "annotations": [{"fingerprint": FP}, {"fingerprint": "b" * 64}]},
    )
    result = measure(tmp_path, load_case("clinica-piloto"), "vulnerable")
    assert result["observacoes"][0]["agente"] == "não avaliado"
    assert "órfão" in result["problemas"][0]["motivo"]


def test_alerta_generico_nao_vira_falso(tmp_path: Path) -> None:
    folder = setup_run(tmp_path)
    data = report()
    data["findings"][0]["path_template"] = "/outro"
    write(folder / "findings.json", data)
    result = measure(tmp_path, load_case("clinica-piloto"), "secure")
    assert result["observacoes"][0]["cli"] == "indeterminado"


@pytest.mark.parametrize("content", ["{", '{"schema_version": true}', "[]"])
def test_arquivo_invalido_nao_e_avaliado(tmp_path: Path, content: str) -> None:
    folder = setup_run(tmp_path)
    (folder / "verification.json").write_text(content, encoding="utf-8")
    result = measure(tmp_path, load_case("clinica-piloto"), "vulnerable")
    assert result["observacoes"][0]["cli"] == "não avaliado"


def test_gabarito_ambiguo_nao_declara_verdade(tmp_path: Path) -> None:
    setup_run(tmp_path)
    case = load_case("clinica-piloto")
    same = case.flaws[0].model_copy(update={"id": "outra"})
    case = case.model_copy(update={"flaws": (*case.flaws, same)})
    result = measure(tmp_path, case, "vulnerable")
    assert result["observacoes"][0]["cli"] == "indeterminado"


def test_dados_suplementares_ausentes_nao_alteram_nota(repo: Path, out: Path) -> None:
    from tests.unit.evals.test_score import good_round, score

    good_round(repo, out)
    result = score(out)
    assert result["grade"] == pytest.approx(10 * (25 + 25 * 0.875 + 20 + 20) / 90, abs=0.01)
    assert result["triage_accuracy"]["problemas"]


def test_correspondencia_parcial_nao_vira_verdade(tmp_path: Path) -> None:
    folder = setup_run(tmp_path)
    data = report()
    data["findings"][0]["title"] = "X-Content-Type-Options Header Missing"
    write(folder / "findings.json", data)
    result = measure(tmp_path, load_case("clinica-piloto"), "secure")
    assert result["observacoes"][0]["cli"] == "indeterminado"


def test_relatorio_de_outra_execucao_nao_e_medido(tmp_path: Path) -> None:
    folder = setup_run(tmp_path)
    write(folder / "findings.json", report("2026-11-13T10-00-01Z-clinica-piloto-bbbb"))
    result = measure(tmp_path, load_case("clinica-piloto"), "vulnerable")
    assert not result["observacoes"]
    assert "divergente" in result["problemas"][0]["motivo"]


def test_versao_de_fingerprint_invalida_nao_e_medida(tmp_path: Path) -> None:
    folder = setup_run(tmp_path)
    data = report()
    data["findings"][0]["fingerprint_version"] = 2
    write(folder / "findings.json", data)
    result = measure(tmp_path, load_case("clinica-piloto"), "vulnerable")
    assert not result["observacoes"]
    assert "fingerprint" in result["problemas"][0]["motivo"]
