"""Prova mínima da pilha crAPI pela CLI; requer laboratório Docker isolado."""

from pathlib import Path

import pytest

from tests.integration.lab_support import REPO, LabCli, require_docker

pytestmark = pytest.mark.integration


def test_crapi_preflight_e_probe_pela_cli(tmp_path: Path) -> None:
    require_docker()
    cli = LabCli(tmp_path, {"HDAST_STACK_PROJECT_SUFFIX": "-codex"})
    for key in tuple(cli.env):
        if key.startswith("CRAPI_"):
            del cli.env[key]
    cli.install_product(
        "crapi", REPO / "lab/crapi/product-profile", (REPO / "lab/crapi/openapi.json",)
    )
    try:
        up = cli.run("stack", "up", "crapi", timeout=600)
        assert up.code == 0, up.stdout + up.stderr
        preflight = cli.run("preflight", "crapi")
        assert preflight.code == 0, preflight.stdout + preflight.stderr
        assert preflight.data["ready"] is True
        checks = {item["id"] for item in preflight.data["checks"] if item["ok"]}
        assert {"login:user_a", "login:user_b"} <= checks
        probe = cli.run("probe", "crapi", "--only", "get_products")
        assert probe.code == 0, probe.stdout + probe.stderr
        assert probe.data["summary"]["successes"] == 1
    finally:
        down = cli.run("stack", "down", timeout=240)
        assert down.code == 0, down.stdout + down.stderr
