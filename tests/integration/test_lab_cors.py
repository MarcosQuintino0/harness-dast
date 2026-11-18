"""Prova direcionada de CORS pelas CLIs e cercas reais, em dois alvos de laboratório."""

import json
from pathlib import Path

import pytest

from tests.integration.lab_support import (
    PILOT_PROFILE,
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    LabCli,
    require_docker,
    run_audit,
)
from tests.integration.run_support import record_metrics, throwaway_pilot_env
from tests.integration.test_lab_vampi import SEEDED

pytestmark = [pytest.mark.integration, pytest.mark.lab_prova]


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("mode", ["vulnerable", "secure"])
def test_cors_em_alvos_do_laboratorio(tmp_path: Path, product: str, mode: str) -> None:
    require_docker()
    env = throwaway_pilot_env()
    env.update(SEEDED)
    cli = LabCli(tmp_path, env)
    if product == "clinica-piloto":
        cli.install_product(product, PILOT_PROFILE)
        operation = "obterPerfil"
    else:
        cli.install_product(product, VAMPI_PROFILE, (VAMPI_OPENAPI,))
        operation = "api_views.users.me"
    flags = ("--build", "--secure") if mode == "secure" else ("--build",)
    try:
        up = cli.run("stack", "up", product, *flags, timeout=600)
        assert up.code == 0, up.stdout + up.stderr
        preflight = cli.run("preflight", product)
        assert preflight.code == 0, preflight.stdout + preflight.stderr
        probe = cli.run("probe", product, "--only", operation, timeout=900)
        assert probe.code == 0, probe.stdout + probe.stderr
        run_id = str(probe.envelope["run_id"])
        result = cli.run("authz", product, "--run", run_id, "--check", "cors", timeout=900)
        assert result.code == 0, result.stdout + result.stderr
        authz = json.loads((cli.runs / run_id / "authz.json").read_text(encoding="utf-8"))
        summary = next(row for row in authz["checks"] if row["check"] == "cors")
        findings = [row for row in authz["findings"] if row["technique"] == "authz_cors"]
        sent = [
            row
            for row in run_audit(cli, run_id)
            if row["phase"] == "decision" and str(row["operation_id"]).startswith("authz:cors:")
        ]
        assert summary["tested"] >= 1, summary
        assert 1 <= len(sent) <= 5
        assert all(row["method"] == "GET" and row["decision"] == "allowed" for row in sent)
        assert len(findings) <= 2
        if product == "clinica-piloto":
            assert bool(findings) == (mode == "vulnerable")
            if findings:
                assert findings[0]["proposed_severity"] == "high"
        payload = {"product": product, "mode": mode, "summary": summary, "findings": findings}
        (tmp_path / "cors-summary.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        record_metrics(f"lab-cors-{product}-{mode}", payload)
    finally:
        cli.stack_down()
