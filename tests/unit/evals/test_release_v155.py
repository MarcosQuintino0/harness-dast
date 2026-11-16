"""Casos da V1.5.5: aprovação fiel à carta e preservação do histórico."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from evals.runner.approve import approve
from evals.runner.cases import EvalError, RoundDirs, load_case
from evals.runner.checks_findings import ACHADA, PARCIAL, flaw_status
from evals.runner.prepare import prepare
from harness_dast.adapters.storage.approval_store import FileApprovalStore
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.domain.scope_approval import check_approval
from tests.unit.evals.support import GOOD_PROFILE, write


def _profile_from_case(name: str) -> dict[str, Any]:
    case = load_case(name)
    expected = case.expected
    profile = copy.deepcopy(GOOD_PROFILE)
    profile.update(
        product=case.product,
        openapi="./openapi.json",
        environment={"name": "lab", "base_url": expected.base_url},
        limits=expected.limits.model_dump(mode="json"),
    )
    profile["scope"] = {
        "allow": [{**rule.model_dump(mode="json"), "allow_local": True} for rule in expected.allow],
        "deny_paths": list(expected.deny_paths),
        "path_mode": expected.path_mode,
        "authorization": {
            "reference": expected.reference,
            "valid_until": expected.valid_until,
        },
        "windows": list(expected.windows),
    }
    profile["auth"] = {
        "type": "login_password",
        "token_path": next(
            path for path in expected.allow[0].paths if path.endswith("/**")
        ).removesuffix("/**")
        + "/login",
        "accounts": [
            {
                "alias": account.alias,
                "role": account.role,
                "username": {"secret_ref": f"env:{account.username_env}"},
                "password": {"secret_ref": f"env:{account.password_env}"},
            }
            for account in expected.accounts
        ],
    }
    profile["authz"] = {
        "allow_writes": expected.allow_authz_writes,
        "shared_roles": list(expected.authz_shared_roles),
    }
    profile["negative"] = {"allow_writes": expected.allow_invalid_input_writes}
    profile["scan"] = {"include_outcomes": list(expected.include_outcomes)}
    return profile


def _prepared_case(repo: Path, out: Path, name: str) -> RoundDirs:
    case = load_case(name)
    for delivered in case.deliver:
        write(repo / delivered.source, '{"openapi":"3.0.0"}')
    result = prepare(name, "vulnerable", 1, out, source=repo)
    assert result.leaks == ()
    folder = result.workspace / "products" / case.product
    write(folder / "target.yml", yaml.safe_dump(_profile_from_case(name)))
    write(folder / "openapi.json", '{"openapi":"3.0.0"}')
    return RoundDirs(out)


@pytest.mark.parametrize("name", ["clinica-piloto", "vampi", "vampi-estrito"])
def test_prepare_e_approve_preservam_permissoes_de_cada_carta(
    repo: Path, out: Path, name: str
) -> None:
    dirs = _prepared_case(repo, out, name)
    product = load_case(name).product

    result = approve(out)

    profile = FileProfileRepository(dirs.workspace / "products").load(product)
    stored = FileApprovalStore(dirs.state).read(product)
    assert result.product == product
    assert check_approval(profile, stored).state == "approved"
    assert profile.authz.allow_writes == load_case(name).expected.allow_authz_writes


def test_caso_historico_recusa_escrita_que_so_a_carta_atual_autoriza(repo: Path, out: Path) -> None:
    dirs = _prepared_case(repo, out, "vampi-estrito")
    current = _profile_from_case("vampi")
    write(dirs.workspace / "products/vampi/target.yml", yaml.safe_dump(current))

    with pytest.raises(EvalError, match="attack_permissions"):
        approve(out)

    assert not (dirs.state / "approvals").exists()


def test_regua_reconhece_cors_e_preserva_cabecalhos_como_parcial() -> None:
    case = load_case("clinica-piloto")
    flaw = next(item for item in case.flaws if item.id == "H3")

    assert flaw_status(flaw, [{"technique": "authz_cors"}]) == ACHADA
    assert flaw_status(flaw, [{"title": "X-Content-Type-Options Header Missing"}]) == PARCIAL


def test_caso_historico_preserva_carta_e_regua_anteriores() -> None:
    old = load_case("vampi-estrito")
    current = load_case("vampi")

    assert old.expected.allow_authz_writes is False
    assert current.expected.allow_authz_writes is True
    assert old.expected.model_copy(update={"allow_authz_writes": True}) == current.expected
    assert all(not item.detectable for item in old.flaws if item.id in {"V3", "V4"})
