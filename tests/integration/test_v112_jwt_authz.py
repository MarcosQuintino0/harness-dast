"""F4 (ADR 0098): JWT no `authz` provado no laboratório local, só leitura e escopo mínimo.

- crAPI: escopo reduzido a `login` e `GET /identity/api/v2/user/dashboard`; o `authz` roda só o
  `tampered_token`. Registra quais variantes o alvo aceitou (inclusive a chave HMAC fraca).
- Clínica Piloto no modo seguro: zero achado de token adulterado.

Use `HDAST_IT_STACK_SUFFIX` para isolar as pilhas. Aprovação descartável do suporte de teste.
"""

import json
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import PILOT_PROFILE, REPO, LabCli, require_docker
from tests.integration.run_support import record_metrics, throwaway_pilot_env
from tests.integration.v112_proof_support import prepare_control_product

pytestmark = pytest.mark.integration


DASHBOARD = "/identity/api/v2/user/dashboard"


def _prepare_crapi_product(products: Path) -> None:
    """Produto descartável do controle, mais a leitura autenticada do painel (`get_dashboard`).

    `get_products` é o caminho de saúde do perfil e o `authz` não o repete; o painel é um `GET`
    autenticado, sem parâmetro e sem efeito, que o escopo reduzido passa a permitir.
    """
    prepare_control_product(products)
    spec_path = products / "crapi" / "openapi.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    full = json.loads((REPO / "lab/crapi/openapi.json").read_text(encoding="utf-8"))
    spec["paths"][DASHBOARD] = {"get": full["paths"][DASHBOARD]["get"]}
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    target = products / "crapi" / "target.yml"
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    data["scope"]["allow"].append(
        dict(data["scope"]["allow"][0], paths=[DASHBOARD], methods=["GET"])
    )
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _authz(cli: LabCli, product: str, run_id: str) -> dict[str, Any]:
    started = time.monotonic()
    done = cli.run("authz", product, "--run", run_id, "--check", "tampered_token", timeout=600)
    assert done.code in {0, 1}, done.stdout[-600:]
    loaded = json.loads((cli.runs / run_id / "authz.json").read_text(encoding="utf-8"))
    return {
        "run_id": run_id,
        "seconds": round(time.monotonic() - started, 1),
        "exit_code": done.code,
        "requests_sent": loaded["requests_sent"],
        "check": next(c for c in loaded["checks"] if c["check"] == "tampered_token"),
        "findings": [
            {k: f[k] for k in ("technique", "proposed_severity", "operation_id", "variants", "cwe")}
            for f in loaded["findings"]
        ],
        "not_tested": [
            {k: n[k] for k in ("check", "operation_id", "reason")} for n in loaded["not_tested"]
        ],
        "serialized": json.dumps(loaded),
    }


def test_crapi_jwt_e_achado_pelo_authz(tmp_path: Path) -> None:
    require_docker()
    cli = LabCli(tmp_path, {})
    for key in tuple(cli.env):
        if key.startswith("CRAPI_"):
            del cli.env[key]
    _prepare_crapi_product(cli.products)
    records: dict[str, Any] = {}
    try:
        assert cli.run("stack", "up", "crapi", timeout=600).code == 0
        assert cli.run("preflight", "crapi").code == 0
        probe = cli.run("probe", "crapi", "--only", "get_dashboard")
        assert probe.code == 0, probe.stdout[-500:]
        run_id = str(probe.envelope["run_id"])
        records.update(_authz(cli, "crapi", run_id))
        serialized = records.pop("serialized")
        assert '"hdast"' not in serialized
        record_metrics("v112-f4-crapi", records)
        assert records["check"]["tested"] >= 1 or records["not_tested"], records
        assert any(
            f["technique"] == "authz_tampered_token" and f["proposed_severity"] == "high"
            for f in records["findings"]
        ), records
    finally:
        cli.stack_down()


def test_clinica_piloto_no_modo_seguro_nao_tem_achado_de_jwt(tmp_path: Path) -> None:
    require_docker()
    cli = LabCli(tmp_path, throwaway_pilot_env())
    cli.install_product("clinica-piloto", PILOT_PROFILE)
    records: dict[str, Any] = {}
    try:
        assert cli.run("stack", "up", "clinica-piloto", "--secure", timeout=900).code == 0
        assert cli.run("preflight", "clinica-piloto").code == 0
        probe = cli.run(
            "probe", "clinica-piloto", "--only", "listarConsultas", "--only", "listarConvenios"
        )
        assert probe.code == 0, probe.stdout[-500:]
        records.update(_authz(cli, "clinica-piloto", str(probe.envelope["run_id"])))
        records.pop("serialized")
        record_metrics("v112-f4-clinica-segura", records)
        assert records["findings"] == [], records
        assert records["check"]["tested"] >= 1, records
    finally:
        cli.stack_down()
