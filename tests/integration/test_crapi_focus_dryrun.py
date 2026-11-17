"""Ensaio crapi-foco sem agente: só o coordenador executa esta integração."""

import json
import shutil
import time
from pathlib import Path
from typing import Any

import pytest

from evals.runner.approve import approve
from evals.runner.cases import EvalError
from evals.runner.metrics import measure_agent
from evals.runner.prepare import prepare
from tests.integration.lab_support import LabCli, require_docker
from tests.integration.run_support import record_metrics
from tests.integration.v112_proof_support import execute, summary

pytestmark = pytest.mark.integration

EXPECTED = {
    "login",
    "contact_mechanic",
    "validate_coupon",
    "get_vehicles",
    "get_location",
    "get_profile_video",
    "update_profile_video",
    "get_products",
}


def _transcript(out: Path, records: dict[str, Any]) -> None:
    """Representação de compatibilidade, gerada do ensaio, não conversa de agente."""
    events = []
    for index, (name, row) in enumerate(records.items()):
        if not isinstance(row, dict) or "started_at" not in row:
            continue
        command = {"up": "stack up", "down": "stack down"}.get(name, name)
        call = f"c{index}"
        events.extend(
            [
                {
                    "type": "assistant",
                    "timestamp": row["started_at"],
                    "message": {
                        "id": call,
                        "content": [
                            {
                                "type": "tool_use",
                                "id": call,
                                "name": "Bash",
                                "input": {"command": f"hdast {command} crapi"},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": row["finished_at"],
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": call,
                                "is_error": row["exit_code"] != 0,
                                "content": "resultado omitido",
                            }
                        ]
                    },
                },
            ]
        )
    (out / "transcript.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in events), encoding="utf-8"
    )


def test_crapi_foco_ensaio_sem_agente(tmp_path: Path) -> None:
    require_docker()
    started = time.monotonic()
    out = tmp_path / "ensaio"
    records: dict[str, Any] = {
        "proveniencia": "ensaio automatizado sem agente; transcript de compatibilidade",
        "meta_segundos": 900,
        "detectable": False,
    }
    try:
        prepared = prepare("crapi-foco", "vulnerable", 0, out)
    except EvalError:
        records["prepare"] = {
            "status": "recusado",
            "detalhes": "verificar diagnostico do runner no terminal",
        }
        record_metrics("v112-crapi-foco-ensaio", records)
        raise
    records["prepare"] = {"exclusoes": list(prepared.excluded), "vazamentos": len(prepared.leaks)}
    cli = LabCli(tmp_path / "isolado", {})
    cli.products = prepared.workspace / "products"
    cli.runs = prepared.workspace / "runs"
    cli.state = out / "state"
    cli.runs.mkdir(exist_ok=True)
    cli.env.update(
        {
            "HDAST_PRODUCTS_DIR": str(cli.products),
            "HDAST_RUNS_DIR": str(cli.runs),
            "HDAST_STATE_DIR": str(cli.state),
        }
    )
    for key in tuple(cli.env):
        if key.startswith("CRAPI_"):
            del cli.env[key]
    stack_attempted = False
    try:
        init = execute(
            cli,
            records,
            "init",
            "init",
            "crapi",
            "--from-letter",
            str(prepared.workspace / "inputs/carta.yml"),
        )
        assert init.code == 0
        shutil.copy2(
            prepared.workspace / "inputs/openapi.json", cli.products / "crapi/openapi.json"
        )
        approve(out)
        records["approval"] = "runner de ensaio"
        stack_attempted = True
        up = execute(cli, records, "up", "stack", "up", "crapi", timeout=600)
        assert up.code == 0
        preflight = execute(cli, records, "preflight", "preflight", "crapi")
        assert preflight.code == 0
        assert preflight.data.get("ready") is True
        checks = {row["id"] for row in preflight.data.get("checks", []) if row.get("ok")}
        assert {"login:user_a", "login:user_b"} <= checks
        probe = execute(cli, records, "probe", "probe", "crapi", timeout=900)
        operations = probe.data.get("operations", [])
        attempts = {
            row.get("operation_id"): row.get("attempts", 0)
            for row in operations
            if row.get("operation_id") in EXPECTED
        }
        records["operacoes"] = attempts
        assert probe.code == 0
        assert probe.data.get("status") == "completed"
        run = execute(cli, records, "run", "run", "crapi", "--max-minutes", "14", timeout=900)
        records["run_summary"] = summary(run)
        assert set(attempts) == EXPECTED
        assert all(value > 0 for value in attempts.values())
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
        assert all(stage["status"] == "ok" for stage in stages)
    finally:
        try:
            if stack_attempted:
                down = execute(cli, records, "down", "stack", "down", timeout=240)
                assert down.code == 0
        finally:
            records["duracao_fim_a_fim_segundos"] = round(time.monotonic() - started, 3)
            if any(isinstance(v, dict) and "started_at" in v for v in records.values()):
                _transcript(out, records)
                metrics = measure_agent(out, "ensaio-sem-agente")
                records["medicao_runner"] = metrics.model_dump(mode="json")
            record_metrics("v112-crapi-foco-ensaio", records)
    assert records["duracao_fim_a_fim_segundos"] <= 900
