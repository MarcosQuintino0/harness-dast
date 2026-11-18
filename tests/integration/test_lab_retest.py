"""Reteste no laboratório (ADR 0112): achar no VAmPI vulnerável, retestar e retestar no modo seguro.

Reproduz o ciclo de uso com um alvo de treino local: o `run` acha a injeção de SQL em
`get_by_username`, o `retestar` repete só essa operação e a vê de novo, e, com o alvo trocado para
o modo seguro (o "conserto"), o mesmo reteste não a reproduz. Prova que o reteste usa o pipeline
do `run` com `--only` e que nenhuma saída afirma correção. Não prova a varredura inteira nem
achados de `authz` ou `negative`, que o reteste não cobre.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.integration.lab_support import VAMPI_OPENAPI, VAMPI_PROFILE, LabCli, require_docker
from tests.integration.test_lab_vampi import SEEDED

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

OPERATION = "api_views.users.get_by_username"
OK_CODES = {0, 1, 3}


@dataclass(frozen=True)
class RetestLab:
    """Artefatos das três execuções do ciclo."""

    first_findings: list[dict[str, Any]]
    vulnerable: dict[str, Any]
    vulnerable_output: str
    secure: dict[str, Any]


def _load(cli: LabCli, run_id: str, name: str) -> dict[str, Any]:
    loaded = json.loads((cli.runs / run_id / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _retest(cli: LabCli, previous: str) -> tuple[dict[str, Any], str]:
    result = cli.run(
        "retestar", "vampi", "--run", previous, "--max", "5", "--max-minutes", "6", timeout=1200
    )
    assert result.code in OK_CODES, result.stdout[-800:]
    retest = result.data["retest"]
    assert isinstance(retest, dict), result.stdout[-800:]
    return retest, result.stdout


def _up(cli: LabCli, *flags: str) -> None:
    up = cli.run("stack", "up", "vampi", *flags, timeout=600)
    assert up.code == 0, up.stdout[-800:] + up.stderr[-800:]


@pytest.fixture(scope="module")
def retest_lab(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RetestLab]:
    require_docker()
    cli = LabCli(Path(tmp_path_factory.mktemp("retest")), SEEDED)
    cli.install_product("vampi", VAMPI_PROFILE, (VAMPI_OPENAPI,))
    try:
        _up(cli, "--vulnerable")
        first = cli.run("run", "vampi", "--only", OPERATION, "--max-minutes", "6", timeout=1500)
        assert first.code in OK_CODES, first.stdout[-800:]
        first_id = str(first.data["run_id"])
        findings = list(_load(cli, first_id, "findings.json")["findings"])
        vulnerable, output = _retest(cli, first_id)
        cli.stack_down()
        _up(cli, "--secure")
        secure, _ = _retest(cli, first_id)
        yield RetestLab(findings, vulnerable, output, secure)
    finally:
        cli.stack_down()


def _sql_fingerprints(findings: list[dict[str, Any]]) -> set[str]:
    return {
        str(item["fingerprint"])
        for item in findings
        if "sql" in str(item["title"]).lower() and item.get("operation_id") == OPERATION
    }


def test_run_only_acha_a_injecao_de_sql_na_operacao_escolhida(retest_lab: RetestLab) -> None:
    assert _sql_fingerprints(retest_lab.first_findings)


def test_reteste_no_alvo_vulneravel_reproduz_a_injecao(retest_lab: RetestLab) -> None:
    by_fingerprint = {e["fingerprint"]: e["result"] for e in retest_lab.vulnerable["entries"]}

    sql = _sql_fingerprints(retest_lab.first_findings)
    assert any(by_fingerprint.get(fp) == "reproduced" for fp in sql), by_fingerprint
    assert retest_lab.vulnerable["only"] == [OPERATION]


def test_reteste_no_alvo_seguro_nao_reproduz_a_injecao(retest_lab: RetestLab) -> None:
    by_fingerprint = {e["fingerprint"]: e["result"] for e in retest_lab.secure["entries"]}

    sql = _sql_fingerprints(retest_lab.first_findings) & set(by_fingerprint)
    assert sql
    assert all(by_fingerprint[fp] == "not_reproduced" for fp in sql), by_fingerprint


def test_reteste_nunca_diz_que_o_achado_foi_corrigido(retest_lab: RetestLab) -> None:
    entries = retest_lab.secure["entries"]
    not_reproduced = [e["reason"] for e in entries if e["result"] == "not_reproduced"]

    assert {e["result"] for e in entries} <= {"reproduced", "not_reproduced", "not_tested"}
    assert "não significa 'corrigido'" in str(retest_lab.secure["notice"])
    assert not_reproduced
    assert all("não prova que o problema foi corrigido" in r for r in not_reproduced)
