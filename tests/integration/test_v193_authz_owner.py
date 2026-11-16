"""Leitura de dono sem roteamento favorável, em dois alvos e modos, só por hdast."""

import json
import secrets
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import PILOT_PROFILE, LabCli, require_docker, run_audit
from tests.integration.run_support import record_metrics, throwaway_pilot_env
from tests.integration.test_lab_v155 import _install
from tests.integration.test_lab_vampi import SEEDED

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]


def _blind_profile(cli: LabCli) -> None:
    """Cópia do lab com consultas no médico compartilhado e pacientes na ordem original."""
    target = cli.install_product("clinica-piloto", PILOT_PROFILE) / "target.yml"
    profile = yaml.safe_load(target.read_text(encoding="utf-8"))
    profile.pop("cleanup", None)
    profile["authz"].update({"allow_writes": True, "shared_roles": ["medico"]})
    # O roteamento de alcance não declara proibições verticais: não presumir hierarquia.
    profile["authz"].pop("role_order", None)
    operations = {"listarConsultas", "buscarConsulta", "criarConsulta", "atualizarStatusConsulta"}
    for rule in profile["auth"]["account_map"]:
        rule["operations"] = [op for op in rule["operations"] if op not in operations]
    profile["auth"]["account_map"].append({"account": "medico_a", "operations": sorted(operations)})
    target.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("mode", ["vulnerable", "secure"])
def test_leitura_de_dono_no_laboratorio(tmp_path: Path, product: str, mode: str) -> None:
    require_docker()
    env = (
        throwaway_pilot_env()
        if product == "clinica-piloto"
        else {**SEEDED, "HDAST_ZAP_API_KEY": secrets.token_hex(32)}
    )
    cli = LabCli(tmp_path, env)
    if product == "clinica-piloto":
        _blind_profile(cli)
    else:
        _install(cli, product)
    commands: list[dict[str, Any]] = []

    def run(*args: str) -> Any:
        done = cli.run(*args, timeout=900)
        commands.append({"args": args, "exit_code": done.code})
        record_metrics(
            f"v193-progress-{product}-{mode}",
            {"commands": commands, "error": done.envelope.get("error")},
        )
        assert done.code == 0, done.envelope.get("error")
        return done

    try:
        run("stack", "up", product, "--build", *(["--secure"] if mode == "secure" else []))
        run("preflight", product)
        # VAmPI: a criação não devolve o título; o leitor não aparece no log do probe.
        flags = ["--only", "api_views.books.add_new_book"] if product == "vampi" else []
        probe = run("probe", product, *flags)
        run_id = str(probe.envelope["run_id"])
        checks = ["--check", "horizontal"] if product == "vampi" else []
        run("authz", product, "--run", run_id, *checks)
        result = json.loads((cli.runs / run_id / "authz.json").read_text(encoding="utf-8"))
        run("panel", product, "--run", run_id)
        page = (cli.runs / run_id / "panel/authorization.html").read_text(encoding="utf-8")
        audit = run_audit(cli, run_id)
        owner = [row for row in audit if str(row["operation_id"]).startswith("authz:owner:")]
        record_metrics(
            f"v193-owner-{product}-{mode}",
            {
                "product": product,
                "mode": mode,
                "run_id": run_id,
                "commands": commands,
                "authz": result,
                "owner_audit": owner,
                "panel_has_gaps": all(
                    n["reason"] in page for n in result["not_tested"] if n["check"] == "horizontal"
                ),
            },
        )
        operation = (
            "buscarConsulta" if product == "clinica-piloto" else "api_views.books.get_by_title"
        )
        found = [
            f
            for f in result["findings"]
            if f["operation_id"] == operation and f["technique"] == "authz_horizontal"
        ]
        assert bool(found) == (mode == "vulnerable")
        assert all(f["proposed_severity"] == "high" for f in found)
        assert owner
        assert all(row["method"] == "GET" for row in owner)
        assert result["status"] == "completed"
        if mode == "secure":
            assert result["findings"] == []
        if product == "clinica-piloto":
            assert any(n["reason"] == "shared_role" for n in result["not_tested"])
            assert not [
                f
                for f in result["findings"]
                if f["technique"] == "authz_horizontal" and f["owner_role"] == "medico"
            ]
            for technique in ("authz_mass_assignment", "authz_excessive_data"):
                assert any(f["technique"] == technique for f in result["findings"]) == (
                    mode == "vulnerable"
                )
    finally:
        cli.stack_down()
