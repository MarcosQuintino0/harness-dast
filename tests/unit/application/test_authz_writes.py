"""`authz`: escrita só com `authz.allow_writes` e estágio que não derruba o `run` (ADR 0038)."""

from typing import Any

import pytest

from harness_dast.application.authz import AuthzRequest
from harness_dast.domain.authz_result import AuthzNotTested, AuthzResult
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.profile import ProductProfile
from tests.fakes.authz_rig import AuthzRig, Clinic, clinic_profile_data

WRITE_CHECKS = ("mass_assignment", "horizontal_write")


def run_authz(rig: AuthzRig, **changes: Any) -> AuthzResult:
    probe = rig.run_probe()
    return rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id, **changes))


def check(result: AuthzResult, name: str) -> Any:
    return next(item for item in result.checks if item.check == name)


def notes(result: AuthzResult, check_name: str, reason: str) -> list[AuthzNotTested]:
    return [n for n in result.not_tested if n.check == check_name and n.reason == reason]


def authz_writes_sent(rig: AuthzRig) -> list[str]:
    return [
        f"{r.method} {r.operation_id}"
        for alias in ("pac_a", "pac_b", "adm")
        for r in rig.sent_by(alias)
        if r.operation_id.startswith("authz:") and r.method in {"POST", "PUT", "PATCH"}
    ]


# --- sem a carta: nada escreve ----------------------------------------------------------


def test_mass_assignment_goes_to_not_tested_and_sends_nothing_without_allow_writes() -> None:
    rig = AuthzRig(Clinic(mass=True), authz={"allow_writes": False})

    result = run_authz(rig, checks=("mass_assignment",))

    assert result.findings == ()
    assert authz_writes_sent(rig) == []
    found = notes(result, "mass_assignment", "writes_not_authorized")
    assert len(found) == 1
    assert "escrita não autorizada pela carta: authz.allow_writes" in found[0].message.lower()
    summary = check(result, "mass_assignment")
    assert summary.status == "skipped"
    assert "authz.allow_writes" in summary.message
    assert rig.clinic.papel["pac_a"] == "paciente"


def test_asking_for_mass_assignment_explicitly_does_not_turn_the_writes_on() -> None:
    rig = AuthzRig(Clinic(mass=True), authz={"allow_writes": False})

    result = run_authz(rig, checks=("horizontal", "mass_assignment"))

    assert result.status == "completed"
    assert authz_writes_sent(rig) == []
    assert notes(result, "mass_assignment", "writes_not_authorized")


def test_the_default_run_without_writes_still_does_the_read_only_checks() -> None:
    rig = AuthzRig(
        Clinic(bola=True, excess=True, mass=True, bfla=True), authz={"allow_writes": False}
    )

    result = run_authz(rig)

    techniques = {f.technique for f in result.findings}
    assert techniques == {"authz_horizontal", "authz_excessive_data", "authz_vertical"}
    assert authz_writes_sent(rig) == []
    assert result.status == "completed"
    assert [c.check for c in result.checks] == [
        "cors",
        "horizontal",
        "excessive_data",
        "anonymous_access",
        "tampered_token",
        "vertical",
        "access_matrix",
        "mass_assignment",
        "horizontal_write",
    ]


def test_write_methods_of_vertical_methods_leave_the_plan_with_a_note() -> None:
    rig = AuthzRig(
        Clinic(bfla=True),
        authz={"vertical_methods": ["GET", "POST"], "allow_writes": False},
    )

    result = run_authz(rig, checks=("vertical",))

    assert {f.operation_id for f in result.findings} == {"listarRelatorios"}
    assert authz_writes_sent(rig) == []
    dropped = notes(result, "vertical", "writes_not_authorized")
    assert len(dropped) == 1
    assert "POST" in dropped[0].message
    assert "GET e HEAD" in dropped[0].message


def test_the_default_vertical_methods_add_no_writes_note() -> None:
    rig = AuthzRig(Clinic(bfla=True), authz={"allow_writes": False})

    result = run_authz(rig, checks=("vertical",))

    assert notes(result, "vertical", "writes_not_authorized") == []


def test_dry_run_without_writes_lists_the_blocked_check() -> None:
    rig = AuthzRig(Clinic(mass=True), authz={"allow_writes": False})

    result = run_authz(rig, dry_run=True)

    assert notes(result, "mass_assignment", "writes_not_authorized")
    assert check(result, "mass_assignment").candidates == 0
    assert authz_writes_sent(rig) == []


def test_a_check_turned_off_by_the_profile_does_not_get_the_writes_note() -> None:
    rig = AuthzRig(
        Clinic(mass=True),
        authz={"allow_writes": False, "disabled_checks": ["mass_assignment"]},
    )

    result = run_authz(rig)

    assert check(result, "mass_assignment").status == "disabled"
    assert notes(result, "mass_assignment", "writes_not_authorized") == []


# --- com a carta: o comportamento anterior ----------------------------------------------


def test_with_allow_writes_the_mass_assignment_runs_and_finds_the_flaw() -> None:
    rig = AuthzRig(Clinic(mass=True), authz={"allow_writes": True})

    result = run_authz(rig, checks=("mass_assignment",))

    assert [f.technique for f in result.findings] == ["authz_mass_assignment"]
    assert notes(result, "mass_assignment", "writes_not_authorized") == []


def test_with_allow_writes_the_write_methods_of_vertical_methods_are_repeated() -> None:
    rig = AuthzRig(
        Clinic(bfla=True),
        authz={"vertical_methods": ["GET", "POST"], "allow_writes": True},
    )

    result = run_authz(rig, checks=("vertical",))

    assert {f.operation_id for f in result.findings} == {"listarRelatorios", "criarConvenio"}


# --- estágio do `run`: não derruba ------------------------------------------------------


def test_missing_exchanges_in_the_run_stage_become_not_tested_instead_of_an_error() -> None:
    rig = AuthzRig(Clinic(bola=True))
    probe = rig.run_probe()
    del rig.store.exchanges[probe.run_id]

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, tolerate_missing_exchanges=True)
    )

    assert result.status == "completed"
    assert result.findings == ()
    assert result.requests_sent == 0
    for name in (
        "cors",
        "horizontal",
        "excessive_data",
        "anonymous_access",
        "tampered_token",
        "vertical",
    ):
        assert notes(result, name, "exchanges_unavailable"), name
    skipped_all = [c for c in result.checks if c.check not in WRITE_CHECKS]
    assert [c.status for c in skipped_all] == ["skipped"] * 7
    assert "exchanges" in notes(result, "horizontal", "exchanges_unavailable")[0].message


def test_missing_exchanges_still_fail_in_the_standalone_command() -> None:
    rig = AuthzRig()
    probe = rig.run_probe()
    del rig.store.exchanges[probe.run_id]

    with pytest.raises(ConfigError, match="exchanges"):
        rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id))


def test_an_exchanges_file_of_another_product_is_refused_even_in_the_tolerant_mode() -> None:
    rig = AuthzRig()
    probe = rig.run_probe()
    rig.store.exchanges[probe.run_id] = ExchangeLog(run_id=probe.run_id, product="outro")

    with pytest.raises(ConfigError, match="outro produto"):
        rig.authz().execute(
            AuthzRequest(product="agenda", run_id=probe.run_id, tolerate_missing_exchanges=True)
        )


@pytest.mark.parametrize("writes", [False, True])
def test_an_empty_exchanges_file_says_why_for_every_check(writes: bool) -> None:
    rig = AuthzRig(Clinic(bola=True), authz={"allow_writes": writes})
    probe = rig.run_probe()
    rig.store.exchanges[probe.run_id] = ExchangeLog(run_id=probe.run_id, product="agenda")

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, tolerate_missing_exchanges=True)
    )

    assert result.status == "completed"
    assert result.requests_sent == 0
    assert result.findings == ()
    for name in ("horizontal", "excessive_data", "vertical", "mass_assignment"):
        assert notes(result, name, "no_exchanges"), name
    assert all(c.status == "skipped" for c in result.checks)
    assert bool(notes(result, "mass_assignment", "writes_not_authorized")) is (not writes)


def test_a_profile_with_a_single_account_does_not_break_the_stage() -> None:
    data = clinic_profile_data()
    data["auth"]["accounts"] = data["auth"]["accounts"][:1]
    data["auth"]["default_account"] = "pac_a"
    data["auth"]["account_map"] = [
        {
            "account": "pac_a",
            "operations": [
                "obterPerfil",
                "atualizarPerfil",
                "buscarConsulta",
                "lerCatalogo",
                "listarRelatorios",
                "criarConvenio",
            ],
        }
    ]
    data["authz"]["role_order"] = ["paciente"]
    data["authz"]["allow_writes"] = False
    rig = AuthzRig(Clinic(bola=True), profile=ProductProfile.from_data(data))

    result = run_authz(rig, tolerate_missing_exchanges=True)

    assert result.status == "completed"
    assert result.findings == ()
    assert notes(result, "horizontal", "no_peer_account")
    assert authz_writes_sent(rig) == []
