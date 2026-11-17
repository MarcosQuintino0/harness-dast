"""Ciclo curto crAPI: execução exclusiva pelo coordenador no laboratório isolado."""

from pathlib import Path
from typing import Any

import pytest

from tests.integration.lab_support import LabCli, require_docker
from tests.integration.run_support import record_metrics
from tests.integration.v112_proof_support import (
    execute,
    prepare_control_product,
    summary,
)

pytestmark = pytest.mark.integration


def test_v112_crapi_cli_cycle(tmp_path: Path) -> None:
    require_docker()
    cli = LabCli(tmp_path, {})
    cli.env["HDAST_STACK_PROJECT_SUFFIX"] = "-codex"
    for key in tuple(cli.env):
        if key.startswith("CRAPI_"):
            del cli.env[key]
    prepare_control_product(cli.products)
    cli.approve_installed_products()
    records: dict[str, Any] = {"scope": "get_products e login", "strength": "LOW explícito"}
    try:
        up = execute(cli, records, "up", "stack", "up", "crapi", timeout=600)
        assert up.code == 0, f"stack up: código {up.code}"
        preflight = execute(cli, records, "preflight", "preflight", "crapi")
        assert preflight.code == 0
        assert preflight.data.get("ready") is True
        checks = {row["id"] for row in preflight.data.get("checks", []) if row.get("ok")}
        assert {"login:user_a", "login:user_b"} <= checks
        probe = execute(cli, records, "probe", "probe", "crapi", "--only", "get_products")
        assert probe.code == 0
        assert probe.data.get("summary", {}).get("successes") == 1
        run = execute(
            cli,
            records,
            "run",
            "run",
            "crapi",
            "--max-minutes",
            "3",
            "--no-authz",
            "--no-negative",
            timeout=300,
        )
        records["run_summary"] = summary(run)
        assert run.code in (0, 1)
        assert records["run_summary"]["run_id"]
        assert records["run_summary"]["status"] in ("completed", "findings")
        stages = records["run_summary"]["stages"]
        assert [stage["name"] for stage in stages] == [
            "preflight",
            "probe",
            "scan",
            "authz",
            "negative",
            "report",
        ]
        assert [stage["status"] for stage in stages] == [
            "ok",
            "ok",
            "ok",
            "skipped",
            "skipped",
            "ok",
        ]
    finally:
        try:
            down = execute(cli, records, "down", "stack", "down", timeout=240)
            assert down.code == 0, f"stack down: código {down.code}"
        finally:
            record_metrics("v112-cli-cycle", records)
