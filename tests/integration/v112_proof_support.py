"""Apoio sanitizado das provas V1.12; não consulta estado ou credenciais."""

import json
import subprocess
from pathlib import Path
from typing import Any

from harness_dast.domain.run import is_run_id
from tests.integration.crapi_support import run_cli
from tests.integration.lab_support import CliResult, LabCli


def control_spec(source: Path, destination: Path) -> None:
    """Mantém somente a operação de controle e os componentes do OpenAPI original."""
    spec = json.loads(source.read_text(encoding="utf-8"))
    path = "/workshop/api/shop/products"
    operation = spec["paths"][path]["get"]
    if operation.get("operationId") != "get_products":
        raise ValueError("Operação de controle inesperada no OpenAPI.")
    spec["paths"] = {path: {"get": operation}}
    destination.write_text(json.dumps(spec), encoding="utf-8")


def execute(
    cli: LabCli, records: dict[str, Any], name: str, *args: str, timeout: int = 420
) -> CliResult:
    """Mede a CLI e registra somente campos conhecidos, sem saídas arbitrárias."""
    try:
        result, timing = run_cli(cli, *args, timeout=timeout)
    except subprocess.TimeoutExpired:
        records[name] = {"status": "timeout", "timeout_seconds": timeout}
        raise
    records[name] = timing
    return result


def summary(result: CliResult) -> dict[str, Any]:
    """Extrai apenas identidade e estado dos estágios, sem mensagens nem artefatos brutos."""
    run_id = result.data.get("run_id") or result.envelope.get("run_id")
    stages = result.data.get("stages")
    return {
        "run_id": run_id if isinstance(run_id, str) and is_run_id(run_id) else None,
        "status": result.data.get("status"),
        "stages": [
            {key: stage.get(key) for key in ("name", "status", "duration_seconds", "run_id")}
            for stage in stages
            if isinstance(stage, dict)
        ]
        if isinstance(stages, list)
        else [],
    }
