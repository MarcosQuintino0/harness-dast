"""Apoio sanitizado das provas V1.12; não consulta estado ou credenciais."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.run import is_run_id
from harness_dast.domain.scope import OutboundRequest
from tests.integration.crapi_support import run_cli
from tests.integration.lab_support import REPO, CliResult, LabCli


def control_spec(source: Path, destination: Path) -> None:
    """Preserva controle, cadastro das contas e metadados do OpenAPI."""
    spec = json.loads(source.read_text(encoding="utf-8"))
    wanted = {"signup", "login", "vehicle_resend_email", "add_vehicle", "get_products"}
    found: set[str] = set()
    paths: dict[str, Any] = {}
    for path, item in spec["paths"].items():
        selected = {
            method: op
            for method, op in item.items()
            if isinstance(op, dict) and op.get("operationId") in wanted
        }
        if selected:
            found.update(op["operationId"] for op in selected.values())
            paths[path] = {
                **{
                    key: value
                    for key, value in item.items()
                    if key
                    not in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
                },
                **selected,
            }
    if found != wanted:
        raise ValueError("Operações de controle ou cadastro ausentes no OpenAPI.")
    spec["paths"] = paths
    destination.write_text(json.dumps(spec), encoding="utf-8")


def narrow_control_profile(products: Path) -> None:
    """Reduz o perfil descartável antes da aprovação e fixa LOW explicitamente."""
    repository = FileProfileRepository(products)
    profile = repository.load("crapi")
    selections = (("POST", "/identity/api/auth/login"), ("GET", "/workshop/api/shop/products"))
    for method, path in selections:
        profile.guard().ensure_allowed(
            OutboundRequest(method=method, url=profile.environment.base_url + path)
        )
    target = products / "crapi" / "target.yml"
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if len(data["scope"]["allow"]) != 1:
        raise ValueError("Perfil de controle inesperado: confira as regras antes de reduzir.")
    original = data["scope"]["allow"][0]
    data["scope"]["allow"] = [
        dict(original, paths=[path], methods=[method]) for method, path in selections
    ]
    data.setdefault("scan", {})["strength"] = "LOW"
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    assert repository.load("crapi").scan.strength == "LOW"


def prepare_control_product(products: Path) -> Path:
    """Cria produto descartável somente com o perfil e o OpenAPI do controle."""
    product = products / "crapi"
    product.mkdir(parents=True, exist_ok=False)
    shutil.copy2(REPO / "lab/crapi/product-profile/target.yml", product / "target.yml")
    control_spec(REPO / "lab/crapi/openapi.json", product / "openapi.json")
    narrow_control_profile(products)
    return product


def probe_attempts(data: dict[str, Any], expected: set[str]) -> tuple[str, dict[str, int]]:
    """Valida o envelope de probe com o modelo da CLI e extrai apenas contagens."""
    result = ProbeResult.model_validate(data)
    return result.status, {
        op.operation_id: op.attempts for op in result.operations if op.operation_id in expected
    }


def install_focus_spec(workspace: Path, products: Path) -> None:
    """Copia o contrato entregue para o caminho gerado pela carta, sem editar o perfil."""
    profile = FileProfileRepository(products).load("crapi")
    target = resolve_product_file(products, "crapi", profile.openapi)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(workspace / "inputs" / "openapi.json", target)


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
