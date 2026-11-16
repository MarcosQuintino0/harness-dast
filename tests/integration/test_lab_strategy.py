"""T2/T4 da estratégia neutra nas duas APIs; exige laboratório exclusivo e local."""

import os
import secrets
from pathlib import Path

import pytest

from tests.integration.lab_support import LabCli, proxy_audit, require_docker
from tests.integration.run_support import (
    Scenario,
    collect_facts,
    record_metrics,
    run_scenario,
    throwaway_pilot_env,
)
from tests.integration.strategy_support import (
    activate_strategy,
    finding_keys,
    install_strategy,
    legacy_anonymous_findings,
    load_artifact,
    record_control,
)
from tests.integration.test_lab_v155 import _install
from tests.integration.test_lab_vampi import SEEDED

pytestmark = pytest.mark.integration
_METRICS_DIR = os.environ.get("HDAST_IT_METRICS_DIR")


@pytest.fixture(autouse=True)
def _metrics_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    # O isolamento global limpa HDAST_*; só restaura o destino explícito e não sensível.
    if _METRICS_DIR is not None:
        monkeypatch.setenv("HDAST_IT_METRICS_DIR", _METRICS_DIR)


def _cli(root: Path, product: str) -> LabCli:
    env = (
        throwaway_pilot_env()
        if product == "clinica-piloto"
        else {**SEEDED, "HDAST_ZAP_API_KEY": secrets.token_hex(32)}
    )
    return LabCli(root, env)


@pytest.mark.lab_fast
@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("mode", ["vulnerable", "secure"])
def test_strategy_preserva_controles_direcionados(tmp_path: Path, product: str, mode: str) -> None:
    """Agrupa a prova em uma pilha por modo para respeitar o orçamento de laboratório.

    A sequência ultrapassa 40 linhas para manter preparação, controles, coleta e encerramento
    no mesmo ciclo de vida, sem reiniciar a pilha entre asserções sobre os mesmos artefatos.
    """
    require_docker()
    cli = _cli(tmp_path, product)
    # Mesma preparação já usada na prova V1.5.5, sem conhecimento no algoritmo/skill.
    _install(cli, product)
    activate_strategy(cli, product)
    flags = ["--build", *(["--secure"] if mode == "secure" else [])]
    try:
        up = cli.run("stack", "up", product, *flags, timeout=900)
        assert up.code == 0, up.stdout + up.stderr
        preflight = cli.run("preflight", product)
        assert preflight.code == 0, preflight.stdout + preflight.stderr
        probe = cli.run("probe", product, timeout=900)
        assert probe.code == 0, probe.stdout + probe.stderr
        run_id = str(probe.envelope["run_id"])
        authz = cli.run("authz", product, "--run", run_id, timeout=900)
        assert authz.code == 0, authz.stdout + authz.stderr
        negative = cli.run("negative", product, "--run", run_id, timeout=900)
        assert negative.code == 0, negative.stdout + negative.stderr
        # Entradas de leitura e uma escrita para conferir identidade e o par XSRF.
        operations = (
            ("buscarPacientesPorNome", "buscarPaciente", "criarConvenio")
            if product == "clinica-piloto"
            else ("api_views.users.get_by_username", "api_views.books.get_by_title")
        )
        only = [value for operation in operations for value in ("--only", operation)]
        scan = cli.run("scan", product, "--run", run_id, *only, timeout=1200)
        assert scan.code == 0, scan.stdout + scan.stderr
        report = cli.run("report", product, "--run", run_id)
        assert report.code in {0, 1}, report.stdout + report.stderr
        zap_findings = load_artifact(cli, run_id, "findings.json")["findings"]
        record_metrics(
            f"v18-t2-{product}-{mode}-detections",
            {
                "findings": [
                    {key: item[key] for key in ("title", "operation_id", "proposed_severity")}
                    for item in zap_findings
                ]
            },
        )
        if mode == "vulnerable":
            assert any(item["title"] == "SQL Injection" for item in zap_findings)
        else:
            assert all(item["proposed_severity"] != "high" for item in zap_findings)
        artifacts = {
            name: load_artifact(cli, run_id, name + ".json")
            for name in ("authz", "negative", "scan")
        }
        record_control(product, mode, artifacts)
        scenario = Scenario(
            f"v18-t2-{product}-{mode}", cli, report, cli.runs / run_id, proxy_audit(cli), {}, 0.0
        )
        base = "http://clinica-piloto:8080" if product == "clinica-piloto" else "http://vampi:5000"
        facts = collect_facts(scenario, base, pilot=product == "clinica-piloto")
        record_metrics(
            f"v18-t2-{product}-{mode}-identity",
            {
                "auth_on_scanner": facts.auth_on_scanner,
                "csrf": facts.csrf,
                "rules_left": facts.rules_left,
                "secret_hits": facts.secret_hits,
            },
        )
        assert facts.rules_left == []
        assert facts.secret_hits == []
        assert facts.auth_on_scanner[0] == facts.auth_on_scanner[1] > 0
        if product == "clinica-piloto":
            assert facts.csrf["writes_reached_target"] > 0
            assert facts.csrf["writes_with_header"] == facts.csrf["writes_reached_target"]
            assert facts.csrf["writes_with_cookie"] == facts.csrf["writes_reached_target"]
            assert facts.csrf["csrf_rejected"] == 0
        assert all(data["status"] == "completed" for data in artifacts.values())
        assert len(artifacts["scan"]["entries"]) == len(operations)
        assert all(item["outcome"] == "completed" for item in artifacts["scan"]["entries"])
        assert not any(row["method"] == "DELETE" for row in proxy_audit(cli))
        assert all(row["host"] == product for row in proxy_audit(cli) if row["decision"] == "allow")
        assert artifacts["scan"]["traffic"]["allowed_outside_allow"] == 0
        if mode == "secure":
            findings = artifacts["authz"]["findings"]
            assert all(item["technique"] == "authz_anonymous_access" for item in findings)
            if findings:
                baseline = legacy_anonymous_findings(cli, product, run_id)
                assert finding_keys(findings) == finding_keys(baseline)
                record_metrics(
                    f"v18-t2-{product}-{mode}-anonymous-baseline",
                    {"with_strategy": finding_keys(findings), "legacy": finding_keys(baseline)},
                )
        if product == "clinica-piloto" and mode == "vulnerable":
            techniques = {item["technique"] for item in artifacts["authz"]["findings"]}
            assert {"authz_horizontal", "authz_mass_assignment", "authz_cors"} <= techniques
    finally:
        cli.stack_down()


@pytest.mark.lab_full
@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
def test_strategy_preserva_varredura_completa(tmp_path: Path, product: str) -> None:
    """Reúne execução e conferências antes de encerrar a única pilha do cenário.

    Ultrapassa 40 linhas porque todas as evidências devem ser coletadas antes do reset;
    nenhuma asserção provoca outra varredura completa.
    """
    require_docker()
    cli = _cli(tmp_path, product)
    install_strategy(cli, product)
    try:
        up = cli.run("stack", "up", product, "--build", timeout=900)
        assert up.code == 0, up.stdout + up.stderr
        scenario = run_scenario(f"v18-t4-{product}", cli, product=product, timeout=3600)
        assert scenario.result.code in {0, 1}, scenario.result.stdout + scenario.result.stderr
        run = scenario.load("run.json")
        scan = scenario.load("scan.json")
        assert run["status"] in {"completed", "findings"}
        assert scan["status"] == "completed"
        assert scan["rules_removed"] is True
        assert scan["entries"]
        assert all(item["outcome"] == "completed" for item in scan["entries"])
        assert all(row["host"] == product for row in scenario.audit if row["decision"] == "allow")
        assert scan["traffic"]["allowed_outside_allow"] == 0
        assert not any(row["method"] == "DELETE" for row in scenario.audit)
        base = "http://clinica-piloto:8080" if product == "clinica-piloto" else "http://vampi:5000"
        facts = collect_facts(scenario, base, pilot=product == "clinica-piloto")
        assert facts.rules_left == []
        assert facts.secret_hits == []
        assert facts.auth_on_scanner[0] == facts.auth_on_scanner[1] > 0
        if product == "clinica-piloto":
            assert facts.notifications == 0
            assert facts.csrf["writes_reached_target"] > 0
            assert facts.csrf["writes_with_header"] == facts.csrf["writes_reached_target"]
            assert facts.csrf["writes_with_cookie"] == facts.csrf["writes_reached_target"]
            assert facts.csrf["csrf_rejected"] == 0
        record_metrics(
            f"v18-t4-{product}-quality",
            {
                "product": product,
                "mode": "vulnerable",
                "run_id": scenario.run_id,
                "status": run["status"],
                "scan_status": scan["status"],
                "entries": scan["entries"],
                "traffic": scan.get("traffic"),
                "findings_by_severity": dict(scenario.by_severity()),
                "finding_titles": dict(scenario.finding_titles()),
                "auth_on_scanner": facts.auth_on_scanner,
                "csrf": facts.csrf,
                "rules_left": facts.rules_left,
                "secret_hits": facts.secret_hits,
            },
        )
    finally:
        cli.stack_down()
