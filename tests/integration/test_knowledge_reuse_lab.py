"""Prova T2 de reutilização entre contextos independentes no laboratório local."""

import os
import secrets
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import CliResult, LabCli, manifest, proxy_audit, require_docker
from tests.integration.reuse_evidence_support import verify_reuse
from tests.integration.run_support import (
    Scenario,
    collect_facts,
    record_metrics,
    throwaway_pilot_env,
)
from tests.integration.strategy_support import load_artifact
from tests.integration.test_lab_mass_assignment_and_pair import _install
from tests.integration.test_lab_vampi import SEEDED

pytestmark = [pytest.mark.integration, pytest.mark.lab_prova]
_METRICS_DIR = os.environ.get("HDAST_IT_METRICS_DIR")


@pytest.fixture(autouse=True)
def _metrics_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    if _METRICS_DIR is not None:
        monkeypatch.setenv("HDAST_IT_METRICS_DIR", _METRICS_DIR)


def _run(
    cli: LabCli, stages: list[dict[str, object]], context: str, *args: str, timeout: int = 900
) -> CliResult:
    stage: dict[str, object] = {
        "context": context,
        "command": " ".join(args[:2]),
        "exit_code": None,
    }
    stages.append(stage)
    result = cli.run(*args, timeout=timeout)
    stage["exit_code"] = result.code
    assert result.code == 0, result.stdout + result.stderr
    return result


def _up(cli: LabCli, stages: list[dict[str, object]], product: str, mode: str, name: str) -> None:
    flags = ["--build", *(["--secure"] if mode == "secure" else [])]
    _run(cli, stages, name, "stack", "up", product, *flags)


def _first_context(
    cli: LabCli, stages: list[dict[str, object]], product: str, mode: str
) -> tuple[str, dict[str, Any]]:
    _install(cli, product)
    try:
        _up(cli, stages, product, mode, "first")
        _run(cli, stages, "first", "preflight", product)
        probe = _run(cli, stages, "first", "probe", product)
        run_id = str(probe.envelope["run_id"])
        _run(cli, stages, "first", "authz", product, "--run", run_id)
        capture = _run(cli, stages, "first", "knowledge", "capture", product, "--run", run_id)
        assert capture.data["activated"] is False
        assert capture.data["approval_changed"] is False
        assert capture.data["copy"] == "knowledge.captured.yml"
        captured = yaml.safe_load(
            (cli.products / product / "knowledge.captured.yml").read_text(encoding="utf-8")
        )
        authz = load_artifact(cli, run_id, "authz.json")
        receipts = authz.get("effects", [])
        assert captured["effects"] == receipts
        if product == "clinica-piloto" and mode == "vulnerable":
            assert receipts, "A prova exige efeito observado, não duas listas vazias"
        assert captured["provenance"]["run_id"] == run_id
        effect = next(entry for entry in captured["entries"] if entry["kind"] == "effect")
        assert effect["state"] == ("validated" if receipts else "proposed")
        return run_id, dict(manifest(cli, run_id)["hashes"])
    finally:
        cli.stack_down()


def _copy_inputs(first: LabCli, second: LabCli, product: str) -> None:
    source = first.products / product
    destination = second.products / product
    destination.mkdir()
    for name in ("target.yml", "data-rules.yml", "flows.yml", "openapi.json", "openapi3.yml"):
        path = source / name
        if path.is_file():
            shutil.copy2(path, destination / name)
    shutil.copy2(source / "knowledge.captured.yml", destination / "knowledge.yml")
    assert not any(second.runs.iterdir())
    assert not any(second.state.iterdir())
    second.approve_installed_products()
    assert (second.state / "approvals" / f"{product}.json").is_file()


def _operations(product: str) -> tuple[str, ...]:
    if product == "clinica-piloto":
        return ("buscarPacientesPorNome", "buscarPaciente", "criarConvenio", "baixarDocumento")
    return ("api_views.users.get_by_username", "api_views.books.get_by_title")


def _record_controls(
    product: str,
    mode: str,
    run_id: str,
    artifacts: dict[str, dict[str, Any]],
    findings: list[dict[str, Any]],
    facts: Any,
) -> None:
    record_metrics(
        f"v19-t2-{product}-{mode}-controls",
        {
            "product": product,
            "mode": mode,
            "run_id": run_id,
            "statuses": {name: data["status"] for name, data in artifacts.items()},
            "operations": list(_operations(product)),
            "findings": [
                {key: item[key] for key in ("title", "operation_id", "proposed_severity")}
                for item in findings
            ],
            "authz_techniques": dict(
                Counter(item["technique"] for item in artifacts["authz"]["findings"])
            ),
            "authz_not_tested": dict(
                Counter(item["reason"] for item in artifacts["authz"].get("not_tested", []))
            ),
            "negative_requests": artifacts["negative"].get("requests_sent"),
            "negative_operations_tested": artifacts["negative"].get("operations_tested"),
            "negative_findings": len(artifacts["negative"].get("findings", [])),
            "negative_by_class": artifacts["negative"].get("by_class"),
            "scan_entries": artifacts["scan"]["entries"],
            "traffic": artifacts["scan"].get("traffic"),
            "identity": facts.auth_on_scanner,
            "csrf": facts.csrf,
            "rules_left": facts.rules_left,
            "secret_hits": facts.secret_hits,
        },
    )


def _verify_controls(
    cli: LabCli, stages: list[dict[str, object]], product: str, mode: str, run_id: str
) -> None:
    operations = _operations(product)
    only = [value for operation in operations for value in ("--only", operation)]
    _run(cli, stages, "second", "authz", product, "--run", run_id)
    verify_reuse(cli, product, mode, run_id)
    _run(cli, stages, "second", "negative", product, "--run", run_id)
    _run(cli, stages, "second", "scan", product, "--run", run_id, *only, timeout=1200)
    report = cli.run("report", product, "--run", run_id)
    stages.append({"context": "second", "command": "report", "exit_code": report.code})
    assert report.code in {0, 1}, report.stdout + report.stderr
    artifacts = {
        name: load_artifact(cli, run_id, name + ".json") for name in ("authz", "negative", "scan")
    }
    findings = load_artifact(cli, run_id, "findings.json")["findings"]
    audit = proxy_audit(cli)
    scenario = Scenario(f"v19-t2-{product}-{mode}", cli, report, cli.runs / run_id, audit, {}, 0.0)
    base = "http://clinica-piloto:8080" if product == "clinica-piloto" else "http://vampi:5000"
    facts = collect_facts(scenario, base, pilot=product == "clinica-piloto")
    _record_controls(product, mode, run_id, artifacts, findings, facts)
    assert all(data["status"] == "completed" for data in artifacts.values())
    assert len(artifacts["scan"]["entries"]) == len(operations)
    assert all(entry["outcome"] == "completed" for entry in artifacts["scan"]["entries"])
    assert artifacts["scan"]["traffic"]["allowed_outside_allow"] == 0
    assert facts.rules_left == []
    assert facts.secret_hits == []
    assert facts.auth_on_scanner[0] == facts.auth_on_scanner[1] > 0
    if mode == "vulnerable":
        assert any(item["title"] == "SQL Injection" for item in findings)
    else:
        assert all(item["proposed_severity"] != "high" for item in findings)
    if product == "clinica-piloto":
        assert any(item["title"] == "Path Traversal" for item in findings) == (mode == "vulnerable")
        assert facts.csrf["writes_reached_target"] > 0
        assert facts.csrf["writes_with_header"] == facts.csrf["writes_reached_target"]
        assert facts.csrf["writes_with_cookie"] == facts.csrf["writes_reached_target"]
        assert facts.csrf["csrf_rejected"] == 0
        if mode == "vulnerable":
            techniques = {item["technique"] for item in artifacts["authz"]["findings"]}
            assert {"authz_horizontal", "authz_mass_assignment", "authz_cors"} <= techniques
    assert not any(row["method"] == "DELETE" for row in audit)
    assert all(row["host"] == product for row in audit if row["decision"] == "allow")


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("mode", ["vulnerable", "secure"])
def test_knowledge_reutiliza_documentos_em_novo_contexto(
    tmp_path: Path, product: str, mode: str
) -> None:
    """Usa duas pilhas sequenciais, sem copiar runs, aprovação ou estado efêmero."""
    require_docker()
    env = (
        throwaway_pilot_env()
        if product == "clinica-piloto"
        else {**SEEDED, "HDAST_ZAP_API_KEY": secrets.token_hex(32)}
    )
    first = LabCli(tmp_path / "first", env)
    second = LabCli(tmp_path / "second", env)
    stages: list[dict[str, object]] = []
    evidence: dict[str, object] = {"product": product, "mode": mode, "stages": stages}
    try:
        first_run, first_hashes = _first_context(first, stages, product, mode)
        evidence["first_hashes"] = first_hashes
        _copy_inputs(first, second, product)
        try:
            _up(second, stages, product, mode, "second")
            _run(second, stages, "second", "preflight", product)
            probe = _run(second, stages, "second", "probe", product)
            second_run = str(probe.envelope["run_id"])
            second_hashes = dict(manifest(second, second_run)["hashes"])
            evidence["second_hashes"] = second_hashes
            assert first_hashes == second_hashes
            assert first_run != second_run
            assert not (second.runs / first_run).exists()
            _verify_controls(second, stages, product, mode, second_run)
        finally:
            second.stack_down()
    finally:
        record_metrics(f"v19-t2-{product}-{mode}-progress", evidence)
