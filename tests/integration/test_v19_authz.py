"""Coleta dirigida do par e da atribuição em massa, sem presumir detecção."""

import json
import secrets
from pathlib import Path

import pytest

from tests.integration.lab_support import LabCli, require_docker, run_audit
from tests.integration.run_support import record_metrics, throwaway_pilot_env
from tests.integration.test_lab_v155 import _install, _summary
from tests.integration.test_lab_vampi import SEEDED

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("mode", ["vulnerable", "secure"])
def test_v19_authz_observacao_dirigida(tmp_path: Path, product: str, mode: str) -> None:
    require_docker()
    env = (
        throwaway_pilot_env()
        if product == "clinica-piloto"
        else {**SEEDED, "HDAST_ZAP_API_KEY": secrets.token_hex(32)}
    )
    cli = LabCli(tmp_path, env)
    _install(cli, product)
    try:
        up = cli.run(
            "stack",
            "up",
            product,
            "--build",
            *(["--secure"] if mode == "secure" else []),
            timeout=900,
        )
        assert up.code == 0
        assert cli.run("preflight", product).code == 0
        probe = cli.run("probe", product, timeout=900)
        assert probe.code == 0
        run_id = str(probe.envelope["run_id"])
        done = cli.run(
            "authz",
            product,
            "--run",
            run_id,
            "--check",
            "horizontal",
            "--check",
            "mass_assignment",
            timeout=900,
        )
        result_path = cli.runs / run_id / "authz.json"
        summary: dict[str, object] = {"product": product, "mode": mode, "exit_code": done.code}
        if result_path.exists():
            data = json.loads(result_path.read_text(encoding="utf-8"))
            summary.update(_summary(product, mode, data))
            summary["not_tested"] = [
                {key: row[key] for key in ("check", "operation_id", "method", "path", "reason")}
                for row in data["not_tested"]
            ]
        summary["pair_audit"] = [
            {
                key: row.get(key)
                for key in (
                    "seq",
                    "phase",
                    "method",
                    "account",
                    "operation_id",
                    "decision",
                    "status",
                    "error",
                )
            }
            for row in run_audit(cli, run_id)
            if row["operation_id"].startswith("authz:pair:")
        ]
        record_metrics(f"v19-authz-{product}-{mode}", summary)
        assert done.code == 0, "Authz interrompido; consulte o resultado e a auditoria sanitizada."
    finally:
        cli.stack_down()
