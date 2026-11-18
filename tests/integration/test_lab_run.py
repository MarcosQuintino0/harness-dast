"""`hdast run` de ponta a ponta contra os alvos de laboratório, com o ZAP 2.17 real.

Cada cenário sobe a pilha gerenciada, roda UM `hdast run` e já coleta tudo o que os testes
conferem (artefatos, trilha do proxy, histórico do ZAP, estado do alvo) antes de a pilha seguinte
substituir a anterior. Os testes só afirmam o que é robusto; o que o ZAP achou ou deixou de achar
é MEDIDO e registrado (`HDAST_IT_METRICS_DIR`), nunca ajustado ao gabarito. Exigem Docker e levam
de 15 a 30 minutos por cenário (limites do perfil de laboratório: 5 req/s, 2 threads).
"""

import time
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from harness_dast.domain.run_summary import STAGES
from tests.integration.lab_support import (
    PILOT_PROFILE,
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    LabCli,
    proxy_audit,
    require_docker,
)
from tests.integration.run_support import (
    Facts,
    Scenario,
    ZapHistory,
    collect_facts,
    parse_ts,
    popen_run,
    record_kill_metrics,
    record_metrics,
    run_scenario,
    save_metrics,
    throwaway_pilot_env,
)

pytestmark = pytest.mark.integration

VAMPI_ENV = {
    "VAMPI_USER_A_USERNAME": "name1",
    "VAMPI_USER_A_PASSWORD": "pass1",
    "VAMPI_USER_B_USERNAME": "name2",
    "VAMPI_USER_B_PASSWORD": "pass2",
    "VAMPI_ADMIN_USERNAME": "admin",
    "VAMPI_ADMIN_PASSWORD": "pass1",
}
RUN_MINUTES = "29"
PILOT_BASE = "http://clinica-piloto:8080"
VAMPI_BASE = "http://vampi:5000"


def _scenario(
    name: str,
    cli: LabCli,
    product: str,
    mode: str,
    base: str,
    *flags: str,
    pilot: bool = False,
) -> Facts:
    """Sobe a pilha no modo pedido, roda `hdast run`, coleta os fatos e derruba a pilha."""
    try:
        assert cli.run("stack", "up", product, mode, timeout=600).code == 0
        scenario = run_scenario(name, cli, "--max-minutes", RUN_MINUTES, *flags, product=product)
        facts = collect_facts(scenario, base, pilot=pilot)
        _report_if_the_run_stopped_before_it(scenario, product)
        record_metrics(
            f"{name}-facts",
            {
                "csrf": facts.csrf,
                "auth_on_scanner": facts.auth_on_scanner,
                "rules_left": facts.rules_left,
                "secret_hits": facts.secret_hits,
                "target_endpoints": len(facts.target_endpoints),
            },
        )
        return facts
    finally:
        cli.stack_down()


def _report_if_the_run_stopped_before_it(scenario: Scenario, product: str) -> None:
    """Como o agente faria: um `run` cortado pelo prazo deixa o `report` por conta de quem o chamou.

    O `scan` parcial grava `scan.json`; o `report` só lê arquivos, então roda mesmo com a pilha
    já derrubada. O resumo do `run` continua com o código do estágio que falhou.
    """
    if (scenario.run_dir / "findings.json").exists() or not (
        scenario.run_dir / "scan.json"
    ).exists():
        return
    done = scenario.cli.run("report", product, "--run", scenario.run_id)
    assert done.code in {0, 1}, done.stdout[-500:]
    save_metrics(scenario)


@pytest.fixture(scope="module")
def vampi_cli(tmp_path_factory: pytest.TempPathFactory) -> LabCli:
    require_docker()
    cli = LabCli(tmp_path_factory.mktemp("vampi-run"), VAMPI_ENV)
    cli.install_product("vampi", VAMPI_PROFILE, (VAMPI_OPENAPI,))
    return cli


@pytest.fixture(scope="module")
def vampi_vulnerable(vampi_cli: LabCli) -> Facts:
    return _scenario("vampi-vulnerable", vampi_cli, "vampi", "--vulnerable", VAMPI_BASE)


@pytest.fixture(scope="module")
def vampi_secure(vampi_cli: LabCli, vampi_vulnerable: Facts) -> Facts:
    return _scenario(
        "vampi-secure",
        vampi_cli,
        "vampi",
        "--secure",
        VAMPI_BASE,
        "--compare",
        vampi_vulnerable.scenario.run_id,
    )


def _pilot(tmp: Path, mode: str, name: str) -> Facts:
    require_docker()
    cli = LabCli(tmp, throwaway_pilot_env())
    cli.install_product("clinica-piloto", PILOT_PROFILE)
    return _scenario(name, cli, "clinica-piloto", mode, PILOT_BASE, pilot=True)


@pytest.fixture(scope="module")
def pilot_vulnerable(tmp_path_factory: pytest.TempPathFactory) -> Facts:
    return _pilot(tmp_path_factory.mktemp("pilot-vuln"), "--vulnerable", "pilot-vulnerable")


@pytest.fixture(scope="module")
def pilot_secure(tmp_path_factory: pytest.TempPathFactory) -> Facts:
    return _pilot(tmp_path_factory.mktemp("pilot-secure"), "--secure", "pilot-secure")


# ------------------------------------------------------------------------------------ comum


def _common_assertions(facts: Facts) -> None:
    scenario = facts.scenario
    summary = scenario.load("run.json")
    assert summary["exit_code"] == scenario.result.code
    assert scenario.result.code in {0, 1, 3}, scenario.result.stdout[-800:]
    assert tuple(stage["name"] for stage in summary["stages"]) == STAGES
    assert summary["stages"][STAGES.index("preflight")]["status"] == "ok"
    assert facts.rules_left == []
    assert facts.secret_hits == []
    scan = scenario.load("scan.json")
    assert scan["rules_removed"] is True
    allowed = [r for r in scenario.audit if r["decision"] == "allow"]
    assert allowed, "o proxy não liberou nada"
    denied_in_scan = [
        r
        for r in scenario.audit
        if r["decision"] == "deny"
        and parse_ts(scan["started_at"]) <= parse_ts(r["ts"]) <= parse_ts(scan["finished_at"])
    ]
    assert scan["traffic"]["denied"] == len(denied_in_scan)
    assert scan["traffic"]["average_rps"] <= scan["traffic"]["limit_rps"] * 1.5
    assert facts.auth_on_scanner[0] == facts.auth_on_scanner[1] > 0


@pytest.mark.lab_full
def test_vampi_vulnerable_run_finds_the_sql_injection_and_leaves_no_trace(
    vampi_vulnerable: Facts,
) -> None:
    _common_assertions(vampi_vulnerable)
    findings = vampi_vulnerable.scenario.findings
    sqli = [f for f in findings if f["title"] == "SQL Injection"]
    assert sqli
    assert all(f["proposed_severity"] == "high" for f in sqli)
    assert all(f["classification"]["cwe"] == 89 for f in sqli)
    assert {r["host"] for r in vampi_vulnerable.scenario.audit if r["decision"] == "allow"} == {
        "vampi"
    }
    assert vampi_vulnerable.scenario.load("run.json")["cleanup_command"] is None


@pytest.mark.lab_full
def test_vampi_secure_run_has_no_high_finding(vampi_secure: Facts) -> None:
    _common_assertions(vampi_secure)
    assert vampi_secure.scenario.by_severity()["high"] == 0, vampi_secure.scenario.finding_titles()
    assert "SQL Injection" not in vampi_secure.scenario.finding_titles()


@pytest.mark.lab_full
def test_compare_marks_persistent_findings_and_reports_the_missing_as_not_observed(
    vampi_secure: Facts, vampi_vulnerable: Facts
) -> None:
    findings = vampi_secure.scenario.load("findings.json")
    marks = Counter(f.get("comparison") for f in findings["findings"])
    assert marks["persistent"] > 0
    not_observed = findings["not_observed"]
    assert any(item["title"] == "SQL Injection" for item in not_observed)
    assert findings["comparison"]["baseline_run_id"] == vampi_vulnerable.scenario.run_id
    report = (vampi_secure.scenario.run_dir / "report.md").read_text(encoding="utf-8")
    assert "não observado" in report.lower()
    assert "foi corrigido" not in report.lower()
    assert "não significa" in report.lower()


# ------------------------------------------------------------------------------------ piloto


def _pilot_common(facts: Facts) -> None:
    _common_assertions(facts)
    assert facts.notifications in {None, 0}
    keys = facts.target_endpoints
    assert not any("/internal" in k or k.startswith("DELETE") for k in keys), keys
    assert not any("/api/notificacoes" in k for k in keys), keys
    audit = facts.scenario.audit
    assert not [r for r in audit if r["decision"] == "allow" and r["method"] == "DELETE"]
    assert {r["host"] for r in audit if r["decision"] == "allow"} == {"clinica-piloto"}
    assert facts.csrf["writes_reached_target"] > 0
    # Cada POST/PUT/PATCH que o varredor mandou ao alvo carregava o par XSRF (cabeçalho e cookie,
    # mesmo valor) e nenhum foi recusado por CSRF: o varredor testa a lógica, não a recusa.
    assert facts.csrf["writes_with_header"] == facts.csrf["writes_reached_target"]
    assert facts.csrf["writes_with_cookie"] == facts.csrf["writes_reached_target"]
    assert facts.csrf["csrf_rejected"] == 0


@pytest.mark.lab_full
def test_pilot_vulnerable_run_scans_and_the_writes_carry_the_xsrf_pair(
    pilot_vulnerable: Facts,
) -> None:
    _pilot_common(pilot_vulnerable)
    titles = pilot_vulnerable.scenario.finding_titles()
    scan = pilot_vulnerable.scenario.load("scan.json")
    scanned = {e["operation_id"] for e in scan["entries"] if e["outcome"] == "completed"}
    if "buscarPacientes" in scanned:
        assert any(
            f["title"] == "SQL Injection" and "busca" in f["path_template"]
            for f in pilot_vulnerable.scenario.findings
        ), titles


@pytest.mark.lab_full
def test_pilot_secure_run_does_not_report_the_planted_weaknesses(pilot_secure: Facts) -> None:
    _pilot_common(pilot_secure)
    titles = pilot_secure.scenario.finding_titles()
    assert "SQL Injection" not in titles
    assert pilot_secure.scenario.by_severity()["high"] == 0, titles


# ------------------------------------------------------------------------------- trava


@pytest.fixture(scope="module")
def kill_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    require_docker()
    cli = LabCli(tmp_path_factory.mktemp("vampi-kill"), VAMPI_ENV)
    cli.install_product("vampi", VAMPI_PROFILE, (VAMPI_OPENAPI,))
    try:
        assert cli.run("stack", "up", "vampi", timeout=600).code == 0
        process = popen_run(cli, "vampi", "--max-minutes", RUN_MINUTES)
        progress = _wait_for_scanning(cli, process)
        started = time.time()
        stop = cli.run("stop")
        # A trava só existe quando o comando `stop` termina (o processo leva 1 a 2 s para iniciar no
        # Windows); medir a partir do disparo contaria como "depois do stop" o que passou antes.
        engaged = time.time()
        stdout, stderr = process.communicate(timeout=120)
        exited = time.time()
        audit = proxy_audit(cli)
        history = ZapHistory(cli.state_file())
        allowed_after = [
            r for r in audit if r["decision"] == "allow" and parse_ts(r["ts"]) > engaged + 1
        ]
        run_dirs = sorted(cli.runs.iterdir())
        outcome = {
            "returncode": process.returncode,
            "stop_code": stop.code,
            "exit_seconds": exited - started,
            "stop_command_seconds": engaged - started,
            "allowed_after_stop": len(allowed_after),
            "last_allowed_offset": max(
                (parse_ts(r["ts"]) - engaged for r in allowed_after), default=0.0
            ),
            "rules_left": [r for r in history.replacer_descriptions() if r.startswith("hdast-")],
            "progress": progress,
            "run_json": _find_run_json(run_dirs),
            "stdout": stdout,
            "stderr": stderr,
        }
        record_kill_metrics(outcome)
        return outcome
    finally:
        cli.stack_down()


def _wait_for_scanning(cli: LabCli, process: Any) -> dict[str, Any]:
    import json

    deadline = time.time() + 900
    while time.time() < deadline and process.poll() is None:
        for path in cli.runs.glob("*/scan-progress.json"):
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if loaded.get("phase") == "scanning" and loaded.get("index", 0) >= 2:
                assert isinstance(loaded, dict)
                return loaded
        time.sleep(2)
    pytest.fail("o run não chegou à varredura a tempo")


def _find_run_json(run_dirs: list[Path]) -> dict[str, Any]:
    import json

    for folder in run_dirs:
        if (folder / "run.json").exists():
            loaded = json.loads((folder / "run.json").read_text(encoding="utf-8"))
            if any(s["name"] == "probe" and s["status"] == "ok" for s in loaded["stages"]):
                assert isinstance(loaded, dict)
                return loaded
    pytest.fail("nenhum run.json com o probe concluído")


@pytest.mark.lab_fast
def test_stop_during_scan_ends_the_run_cleanly_within_seconds(kill_run: dict[str, Any]) -> None:
    assert kill_run["stop_code"] == 0
    assert kill_run["returncode"] == 130
    assert kill_run["exit_seconds"] < 60
    assert kill_run["allowed_after_stop"] == 0
    assert kill_run["rules_left"] == []
    summary = kill_run["run_json"]
    assert summary["status"] == "interrupted"
    assert summary["stop_requested"] is True
    # Desde o ADR 0025 o relatório sai mesmo com a varredura interrompida, sobre o que foi
    # coletado e sem tráfego novo ao alvo; a saída continua 130.
    assert any(s["name"] == "report" and s["status"] == "ok" for s in summary["stages"])
