"""`evals.runner approve`: o coordenador aprova o escopo da rodada depois de conferir a carta."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from evals.runner.approve import approve
from evals.runner.cases import EvalError, RoundDirs
from harness_dast.adapters.storage.approval_store import FileApprovalStore
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.domain.scope_approval import check_approval
from tests.unit.evals.support import CASES, GOOD_PROFILE, make_round, write

PROFILE: dict[str, Any] = {
    **copy.deepcopy(GOOD_PROFILE),
    "openapi": "./openapi.json",
}
PROFILE["scope"]["allow"][0]["allow_local"] = True
PROFILE["auth"] = {
    "type": "login_password",
    "token_path": "/api/login",
    "accounts": [
        {
            "alias": "admin_a",
            "role": "admin",
            "username": {"secret_ref": "env:MINI_ADMIN_USER"},
            "password": {"secret_ref": "env:MINI_ADMIN_PASS"},
        }
    ],
}


def install(dirs: RoundDirs, profile: dict[str, Any]) -> None:
    write(dirs.workspace / "products" / "mini" / "target.yml", yaml.safe_dump(profile))
    write(dirs.workspace / "products" / "mini" / "openapi.json", "{}")


def test_approve_writes_the_approval_in_the_round_state_dir(repo: Path, out: Path) -> None:
    dirs = make_round(repo, out)
    install(dirs, PROFILE)

    result = approve(out, cases_dir=CASES)

    assert result.file == dirs.state / "approvals" / "mini.json"
    profile = FileProfileRepository(dirs.workspace / "products").load("mini")
    stored = FileApprovalStore(dirs.state).read("mini")
    assert check_approval(profile, stored).state == "approved"


def test_approve_refuses_a_profile_that_widens_the_letter_and_writes_nothing(
    repo: Path, out: Path
) -> None:
    dirs = make_round(repo, out)
    wider = copy.deepcopy(PROFILE)
    wider["scope"]["allow"][0]["methods"] = ["DELETE", "GET", "POST"]
    install(dirs, wider)

    with pytest.raises(EvalError) as caught:
        approve(out, cases_dir=CASES)

    assert "allow" in str(caught.value)
    assert not (dirs.state / "approvals").exists()


def test_approve_refuses_a_wide_path_mode_the_letter_does_not_give(repo: Path, out: Path) -> None:
    dirs = make_round(repo, out)
    wide = copy.deepcopy(PROFILE)
    wide["scope"]["path_mode"] = "wide"
    install(dirs, wide)

    with pytest.raises(EvalError) as caught:
        approve(out, cases_dir=CASES)

    assert "path_mode" in str(caught.value)


def test_approve_asks_for_a_prepared_round_and_a_profile(repo: Path, out: Path) -> None:
    with pytest.raises(EvalError):
        approve(out, cases_dir=CASES)
    make_round(repo, out)

    with pytest.raises(EvalError) as caught:
        approve(out, cases_dir=CASES)

    assert "nao cadastrou" in str(caught.value)


def test_approve_refuses_a_profile_that_does_not_validate(repo: Path, out: Path) -> None:
    dirs = make_round(repo, out)
    broken = copy.deepcopy(PROFILE)
    del broken["auth"]["type"]
    install(dirs, broken)

    with pytest.raises(EvalError):
        approve(out, cases_dir=CASES)


def test_approve_again_after_the_agent_edits_a_protected_block_approves_the_new_one(
    repo: Path, out: Path
) -> None:
    dirs = make_round(repo, out)
    install(dirs, PROFILE)
    approve(out, cases_dir=CASES)
    narrower = copy.deepcopy(PROFILE)
    narrower["limits"]["requests_per_second"] = 5
    install(dirs, narrower)
    profile = FileProfileRepository(dirs.workspace / "products").load("mini")
    assert check_approval(profile, FileApprovalStore(dirs.state).read("mini")).state == "changed"

    approve(out, cases_dir=CASES)

    assert check_approval(profile, FileApprovalStore(dirs.state).read("mini")).state == "approved"


@pytest.mark.parametrize(
    ("block", "field", "value"),
    [
        ("authz", "allow_writes", True),
        ("negative", "allow_writes", True),
        ("scan", "allow_upload_scan", True),
        ("scan", "include_outcomes", ["not_found"]),
    ],
)
def test_approve_recusa_permissao_nao_autorizada(
    repo: Path, out: Path, block: str, field: str, value: object
) -> None:
    dirs = make_round(repo, out)
    profile = copy.deepcopy(PROFILE)
    profile[block] = {field: value}
    install(dirs, profile)

    with pytest.raises(EvalError, match="attack_permissions"):
        approve(out, cases_dir=CASES)
    assert not (dirs.state / "approvals").exists()


@pytest.mark.parametrize(
    ("block", "value"),
    [("authz", None), ("negative", []), ("scan", "invalido"), ("authz", {"allow_writes": "true"})],
)
def test_approve_recusa_formato_de_ataque_invalido(
    repo: Path, out: Path, block: str, value: object
) -> None:
    dirs = make_round(repo, out)
    profile = copy.deepcopy(PROFILE)
    profile[block] = value
    install(dirs, profile)

    with pytest.raises(EvalError, match="attack_permissions"):
        approve(out, cases_dir=CASES)
    assert not (dirs.state / "approvals").exists()
