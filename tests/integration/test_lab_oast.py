"""Callback real com emissor sintético; não é prova do SSRF do crAPI."""

import os
import secrets
import time
from pathlib import Path

import pytest

from harness_dast.domain.run import RunId
from tests.integration.lab_support import REPO, VAMPI_OPENAPI, VAMPI_PROFILE, LabCli, require_docker
from tests.integration.oast_support import OastLab, install_vampi
from tests.integration.run_support import record_metrics
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


def test_callback_e_isolamento_a_partir_do_workshop_crapi(tmp_path: Path) -> None:
    """Prova infraestrutura; não executa SSRF ou contorna o gate de execução."""
    assert os.environ.get("HDAST_IT_METRICS_DIR"), "Defina HDAST_IT_METRICS_DIR para a evidência."
    require_docker()
    key = secrets.token_hex(32)
    token = secrets.token_hex(8)
    extra = {
        "HDAST_ZAP_API_KEY": key,
        "HDAST_STACK_PROJECT_SUFFIX": "-codex",
        "CRAPI_DB_PASSWORD": secrets.token_hex(16),
        "CRAPI_USER_A_EMAIL": f"a.{token}@example.com",
        "CRAPI_USER_B_EMAIL": f"b.{token}@example.com",
        "CRAPI_USER_A_PASSWORD": "Aa1#" + secrets.token_hex(16),
        "CRAPI_USER_B_PASSWORD": "Aa1#" + secrets.token_hex(16),
    }
    cli = LabCli(tmp_path, extra)
    for name in tuple(cli.env):
        if name.startswith("CRAPI_") and name not in extra:
            del cli.env[name]
    cli.env["HDAST_STACK_PROJECT_SUFFIX"] = "-codex"
    cli.install_product(
        "crapi", REPO / "lab/crapi/product-profile", (REPO / "lab/crapi/openapi.json",)
    )
    marker = "lab-" + secrets.token_hex(6)
    lab = OastLab(cli, key, secrets.token_hex(6))
    lab.assert_project_unused()
    lab.assert_crapi_unused()
    try:
        up = cli.run("stack", "up", "crapi", timeout=900)
        assert up.code == 0, "Falha ao subir a pilha crAPI de teste."
        run_id = up.data.get("run_id")
        assert isinstance(run_id, str)
        assert run_id
        RunId(value=run_id)
        assert "-crapi-" in run_id
        lab.start(synthetic=False)
        lab.attach_workshop()
        lab.topology(workshop=True)
        before = lab.interaction_count()
        lab.invoke(marker)
        for _ in range(30):
            if lab.has_event(marker):
                break
            time.sleep(0.2)
        assert lab.has_event(marker)
        after = lab.interaction_count()
        assert after == before + 1
        lab.assert_no_external_route()
        record_metrics(
            f"oast-crapi-callback-{run_id}",
            {
                "stack_run_id": run_id,
                "marker": marker,
                "callback_before": before,
                "callback_after": after,
                "source": "crapi-workshop",
                "external": "ENETUNREACH",
            },
        )
    finally:
        try:
            lab.close()
        finally:
            cli.stack_down()
