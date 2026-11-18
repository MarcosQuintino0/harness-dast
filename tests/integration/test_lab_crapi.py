"""Prova mínima da pilha crAPI pela CLI; requer laboratório Docker isolado."""

from pathlib import Path
from typing import Any

import pytest

from harness_dast.domain.run import is_run_id
from tests.integration.crapi_support import (
    assert_volumes_removed,
    inspect_topology,
    observe_status,
    run_cli,
)
from tests.integration.lab_support import REPO, LabCli, require_docker
from tests.integration.run_support import record_metrics

pytestmark = pytest.mark.integration


def test_crapi_preflight_e_probe_pela_cli(tmp_path: Path) -> None:
    require_docker()
    cli = LabCli(tmp_path, {})
    for key in tuple(cli.env):
        if key.startswith("CRAPI_"):
            del cli.env[key]
    cli.install_product(
        "crapi", REPO / "lab/crapi/product-profile", (REPO / "lab/crapi/openapi.json",)
    )
    # Somente suporte de teste prepara a aprovação; nenhuma observação posterior a regrava.
    cli.approve_installed_products()
    metrics: dict[str, Any] = {}
    up_ok = False
    topology_ok = False
    volumes: set[str] = set()
    try:
        metrics["before_up"] = observe_status(cli)
        up, metrics["up"] = run_cli(cli, "stack", "up", "crapi", timeout=600)
        assert up.code == 0, up.stdout + up.stderr
        up_ok = True
        metrics["before_preflight"] = observe_status(cli)
        assert metrics["before_preflight"]["binding"] == "fresh"
        assert metrics["before_preflight"]["approval_state"] == "approved"
        assert metrics["before_preflight"]["approval_time"] == metrics["before_up"]["approval_time"]
        before = {p.name for p in cli.runs.iterdir() if p.is_dir()}
        preflight, metrics["preflight"] = run_cli(cli, "preflight", "crapi")
        candidates = sorted(
            p.name
            for p in cli.runs.iterdir()
            if p.is_dir() and p.name not in before and is_run_id(p.name)
        )
        metrics["preflight"]["run_id_candidates"] = candidates
        if metrics["preflight"]["run_id"] is None and len(candidates) == 1:
            metrics["preflight"]["run_id"] = candidates[0]
            metrics["preflight"]["run_id_source"] = "new_run_directory"
        metrics["after_preflight"] = observe_status(cli)
        assert metrics["after_preflight"]["binding"] == "fresh"
        assert metrics["after_preflight"]["approval_state"] == "approved"
        assert metrics["after_preflight"]["approval_time"] == metrics["before_up"]["approval_time"]
        assert preflight.code == 0, preflight.stdout + preflight.stderr
        assert preflight.data["ready"] is True
        checks = {item["id"] for item in preflight.data["checks"] if item["ok"]}
        assert {"login:user_a", "login:user_b"} <= checks
        probe, metrics["probe"] = run_cli(cli, "probe", "crapi", "--only", "get_products")
        assert probe.code == 0, probe.stdout + probe.stderr
        assert probe.data["summary"]["successes"] == 1
    finally:
        try:
            if up_ok:
                metrics["topology"] = "failed"
                volumes = inspect_topology()
                topology_ok = True
                metrics["topology"] = "passed"
                metrics["volume_count"] = len(volumes)
        finally:
            try:
                down, metrics["down"] = run_cli(cli, "stack", "down", timeout=240)
                if topology_ok and down.code == 0:
                    metrics["volumes_removed"] = False
                    assert_volumes_removed(volumes)
                    metrics["volumes_removed"] = True
                assert down.code == 0, down.stdout + down.stderr
            finally:
                record_metrics("v112-l1-crapi", metrics)
