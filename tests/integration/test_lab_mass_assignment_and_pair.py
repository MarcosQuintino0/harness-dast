"""Provas V1.5.5 em duas APIs reais: mesma conta escritora e par com recurso novo."""

import json
import secrets
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import (
    PILOT_PROFILE,
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    LabCli,
    proxy_audit,
    require_docker,
    run_audit,
)
from tests.integration.run_support import record_metrics, throwaway_pilot_env
from tests.integration.test_lab_vampi import SEEDED

pytestmark = [pytest.mark.integration, pytest.mark.lab_prova]


def _install(cli: LabCli, product: str) -> None:
    source = PILOT_PROFILE if product == "clinica-piloto" else VAMPI_PROFILE
    extras = () if product == "clinica-piloto" else (VAMPI_OPENAPI,)
    folder = cli.install_product(product, source, extras)
    target = folder / "target.yml"
    profile = yaml.safe_load(target.read_text(encoding="utf-8"))
    profile.pop("cleanup", None)
    profile["scope"]["allow"][0]["methods"] = [
        method for method in profile["scope"]["allow"][0]["methods"] if method != "DELETE"
    ]
    profile["authz"] = {"allow_writes": True}
    if product == "vampi":
        profile["authz"]["public_operations"] = ["api_views.users.get_by_username"]
    if product == "clinica-piloto":
        profile["authz"]["shared_roles"] = ["medico"]
        # A criação exige referência ao próprio dono. O perfil declara esse vínculo;
        # a regra do harness não infere posse por nomes de campo ou de papel.
        accounts = profile["auth"]["accounts"]
        first = next(item for item in accounts if item["alias"] == "paciente_b")
        accounts.remove(first)
        accounts.insert(0, first)
        flow_path = folder / "flows.yml"
        flows = yaml.safe_load(flow_path.read_text(encoding="utf-8"))
        for binding in flows["bindings"]:
            binding["consumed_by"] = [
                consumer
                for consumer in binding["consumed_by"]
                if not (
                    consumer["operation"] == "criarConsulta"
                    and consumer.get("field") == "pacienteId"
                )
            ]
        flows["bindings"].append(
            {
                "produces": {"operation": "obterPerfil", "field": "pacienteId"},
                "consumed_by": [{"operation": "criarConsulta", "field": "pacienteId"}],
            }
        )
        flow_path.write_text(yaml.safe_dump(flows), encoding="utf-8")
        for rule in profile["auth"]["account_map"]:
            rule["operations"] = [
                operation
                for operation in rule["operations"]
                if operation not in {"obterPerfil", "buscarConsulta"}
            ]
        profile["auth"]["account_map"].extend(
            [
                {"account": "paciente_b", "operations": ["obterPerfil"]},
                {"account": "medico_a", "operations": ["buscarConsulta"]},
            ]
        )
    target.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")


def _summary(product: str, mode: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "product": product,
        "mode": mode,
        "run_id": data["run_id"],
        "status": data["status"],
        "requests_sent": data["requests_sent"],
        "created_resources": data["created_resources"],
        "checks": data["checks"],
        "findings": [
            {
                key: finding[key]
                for key in (
                    "technique",
                    "operation_id",
                    "method",
                    "path_template",
                    "actor_account",
                    "actor_role",
                    "owner_account",
                    "owner_role",
                    "proposed_severity",
                    "fields",
                    "candidate_source",
                )
            }
            for finding in data["findings"]
        ],
        "not_tested_reasons": dict(Counter(item["reason"] for item in data["not_tested"])),
    }


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("mode", ["vulnerable", "secure"])
def test_mass_e_par_automatico_nas_duas_apis(tmp_path: Path, product: str, mode: str) -> None:
    require_docker()
    env = (
        throwaway_pilot_env()
        if product == "clinica-piloto"
        else {
            **SEEDED,
            "HDAST_ZAP_API_KEY": secrets.token_hex(32),
        }
    )
    cli = LabCli(tmp_path, env)
    _install(cli, product)
    try:
        flags = [*(["--secure"] if mode == "secure" else [])]
        up = cli.stack_up(product, *flags, timeout=900)
        assert up.code == 0, up.stdout[-1500:] + up.stderr[-1500:]
        assert cli.run("preflight", product).code == 0
        probe = cli.run("probe", product, timeout=900)
        assert probe.code == 0, probe.stdout[-1500:]
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
        assert done.code == 0, done.stdout[-1500:] + done.stderr[-1500:]
        data = json.loads((cli.runs / run_id / "authz.json").read_text(encoding="utf-8"))
        rows = run_audit(cli, run_id)
        posts = [
            row
            for row in rows
            if row["phase"] == "result"
            and row["method"] == "POST"
            and row["operation_id"].startswith("authz:pair:")
        ]
        summary = _summary(product, mode, data)
        summary["pair_posts"] = len(posts)
        summary["pair_post_accounts"] = sorted({row["account"] for row in posts})
        (tmp_path / "v155-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        record_metrics(f"v155-{product}-{mode}", summary)
        assert data["status"] == "completed"
        assert posts, "O par automático deve tentar criar com contas do perfil."
        assert all(row["method"] != "DELETE" for row in proxy_audit(cli))
        assert all(row["host"] == product for row in proxy_audit(cli))
        if product == "clinica-piloto":
            pair_findings = [
                f
                for f in data["findings"]
                if f["technique"] == "authz_horizontal" and f["owner_role"] == "paciente"
            ]
            mass_findings = [
                f
                for f in data["findings"]
                if f["technique"] == "authz_mass_assignment" and f["path_template"] == "/api/me"
            ]
            assert bool(pair_findings) == (mode == "vulnerable")
            assert bool(mass_findings) == (mode == "vulnerable")
            assert any(item["reason"] == "shared_role" for item in data["not_tested"])
            assert not any(
                f["technique"] == "authz_horizontal" and f["owner_role"] == "medico"
                for f in data["findings"]
            )
            if mode == "vulnerable":
                assert "paciente_b" in summary["pair_post_accounts"]
                exchanges = json.loads(
                    (cli.runs / run_id / "exchanges.json").read_text(encoding="utf-8")
                )
                recorded = {item["operation_id"]: item for item in exchanges["exchanges"]}
                assert recorded["obterPerfil"]["account"] == "paciente_b"
                assert recorded["atualizarPerfil"]["account"] == "paciente_a"
                confirmations = [
                    row
                    for row in rows
                    if row["phase"] == "result"
                    and row["operation_id"] == "authz:obterPerfil"
                    and row["account"] == "paciente_a"
                ]
                assert len(confirmations) >= 2
        else:
            assert any(row["account"] == "user_a" for row in posts)
        if mode == "secure":
            assert data["findings"] == []
    finally:
        cli.stack_down()
