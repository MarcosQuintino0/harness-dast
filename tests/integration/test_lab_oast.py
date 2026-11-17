"""Callback real com emissor sintético; não é prova do SSRF do crAPI."""

import secrets
import time
from pathlib import Path

import pytest

from tests.integration.lab_support import VAMPI_OPENAPI, VAMPI_PROFILE, LabCli, require_docker
from tests.integration.oast_support import OastLab, install_vampi
from tests.integration.test_lab_vampi import SEEDED

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]


def test_callback_e_isolamento_com_emissor_sintetico(tmp_path: Path) -> None:
    require_docker()
    key = secrets.token_hex(32)
    cli = LabCli(tmp_path, {**SEEDED, "HDAST_ZAP_API_KEY": key})
    cli.env["HDAST_STACK_PROJECT_SUFFIX"] = "-codex"
    install_vampi(cli, VAMPI_PROFILE, VAMPI_OPENAPI)
    marker = "lab-" + secrets.token_hex(6)
    lab = OastLab(cli, key, secrets.token_hex(6))
    lab.assert_project_unused()
    try:
        up = cli.run("stack", "up", "vampi", timeout=900)
        assert up.code == 0, up.stdout + up.stderr
        lab.start()
        lab.topology()
        before = lab.interaction_count()
        lab.invoke(marker)
        for _ in range(30):
            if lab.has_event(marker):
                break
            time.sleep(0.2)
        assert lab.has_event(marker)
        assert lab.interaction_count() == before + 1
        lab.assert_no_external_route()
    finally:
        try:
            lab.close()
        finally:
            cli.stack_down()
