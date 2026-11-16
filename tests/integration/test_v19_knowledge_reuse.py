"""Prova T2 de reutilização entre contextos independentes no laboratório local."""

import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.integration.lab_support import LabCli, proxy_audit, require_docker
from tests.integration.run_support import record_metrics, throwaway_pilot_env
from tests.integration.strategy_support import load_artifact
from tests.integration.test_lab_v155 import _install
from tests.integration.test_lab_vampi import SEEDED

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]
_METRICS_DIR = os.environ.get("HDAST_IT_METRICS_DIR")


@pytest.fixture(autouse=True)
def _metrics_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    if _METRICS_DIR is not None:
        monkeypatch.setenv("HDAST_IT_METRICS_DIR", _METRICS_DIR)


def _run(cli: LabCli, *args: str, timeout: int = 900) -> Any:
    result = cli.run(*args, timeout=timeout)
    assert result.code == 0, result.stdout + result.stderr
    return result


def _up(cli: LabCli, product: str, mode: str) -> None:
    flags = ["--build", *(["--secure"] if mode == "secure" else [])]
    _run(cli, "stack", "up", product, *flags)


def _first_context(cli: LabCli, product: str, mode: str) -> str:
    _install(cli, product)
    try:
        _up(cli, product, mode)
        _run(cli, "preflight", product)
        probe = _run(cli, "probe", product)
        capture = _run(cli, "knowledge", "capture", product)
        assert capture.data["activated"] is False
        assert capture.data["approval_changed"] is False
        assert capture.data["copy"] == "knowledge.captured.yml"
        return str(probe.envelope["run_id"])
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
        return ("buscarPacientesPorNome", "buscarPaciente", "criarConvenio")
    return ("api_views.users.get_by_username", "api_views.books.get_by_title")


def _verify_controls(cli: LabCli, product: str, mode: str, run_id: str) -> None:
    operations = _operations(product)
    only = [value for operation in operations for value in ("--only", operation)]
    _run(cli, "authz", product, "--run", run_id)
    _run(cli, "negative", product, "--run", run_id)
    _run(cli, "scan", product, "--run", run_id, *only, timeout=1200)
    report = cli.run("report", product, "--run", run_id)
    assert report.code in {0, 1}, report.stdout + report.stderr
    artifacts = {
        name: load_artifact(cli, run_id, name + ".json") for name in ("authz", "negative", "scan")
    }
    findings = load_artifact(cli, run_id, "findings.json")["findings"]
    assert all(data["status"] == "completed" for data in artifacts.values())
    assert len(artifacts["scan"]["entries"]) == len(operations)
    assert all(entry["outcome"] == "completed" for entry in artifacts["scan"]["entries"])
    assert artifacts["scan"]["traffic"]["allowed_outside_allow"] == 0
    if mode == "vulnerable":
        assert any(item["title"] == "SQL Injection" for item in findings)
    else:
        assert all(item["proposed_severity"] != "high" for item in findings)
    if product == "clinica-piloto" and mode == "vulnerable":
        techniques = {item["technique"] for item in artifacts["authz"]["findings"]}
        assert {"authz_horizontal", "authz_mass_assignment", "authz_cors"} <= techniques
    audit = proxy_audit(cli)
    assert not any(row["method"] == "DELETE" for row in audit)
    assert all(row["host"] == product for row in audit if row["decision"] == "allow")
    record_metrics(
        f"v19-t2-{product}-{mode}",
        {
            "product": product,
            "mode": mode,
            "run_id": run_id,
            "statuses": {name: data["status"] for name, data in artifacts.items()},
            "operations": list(operations),
            "findings": [
                {key: item[key] for key in ("title", "operation_id", "proposed_severity")}
                for item in findings
            ],
        },
    )


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("mode", ["vulnerable", "secure"])
def test_knowledge_reutiliza_documentos_em_novo_contexto(
    tmp_path: Path, product: str, mode: str
) -> None:
    """Usa duas pilhas sequenciais, sem copiar runs, aprovação ou estado efêmero."""
    require_docker()
    env = throwaway_pilot_env() if product == "clinica-piloto" else dict(SEEDED)
    first = LabCli(tmp_path / "first", env)
    second = LabCli(tmp_path / "second", env)
    first_run = _first_context(first, product, mode)
    _copy_inputs(first, second, product)
    try:
        _up(second, product, mode)
        _run(second, "preflight", product)
        probe = _run(second, "probe", product)
        second_run = str(probe.envelope["run_id"])
        assert first_run != second_run
        assert not (second.runs / first_run).exists()
        _verify_controls(second, product, mode, second_run)
    finally:
        second.stack_down()
