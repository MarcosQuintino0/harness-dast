"""`keyring:` no `preflight`, no `doctor` e no `probe`: presença, dica e redação (ADR 0030)."""

import json
from pathlib import Path
from typing import Any

from harness_dast.application.doctor import Doctor
from harness_dast.application.probe import ProbeRequest
from harness_dast.application.secret_router import RoutingSecretProvider
from harness_dast.application.validate_profile import ValidateProfile
from harness_dast.domain.profile import ProductProfile
from harness_dast.observability.logging import MASK, SecretRegistry
from tests.fakes.approvals import InMemoryApprovalStore
from tests.fakes.credential_store import InMemoryCredentialStore
from tests.fakes.host import FakeHost
from tests.fakes.probe_ports import DictSecretProvider
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.rig import ENV, LOGIN, PASSWORD, TOKEN, Rig, agenda_profile, profile_data
from tests.fakes.runtime import ManualClock
from tests.fakes.stack import InMemoryStackState

VAULT_NAME = "ACME_USER_A_SENHA"


def keyring_profile() -> ProductProfile:
    auth = profile_data()["auth"]
    auth["accounts"][0]["password"] = {"secret_ref": f"keyring:{VAULT_NAME}"}
    return agenda_profile(auth=auth)


def rig_with(store: InMemoryCredentialStore) -> Rig:
    rig = Rig(profile=keyring_profile(), env={"ACME_USER_A_LOGIN": LOGIN})
    rig.secrets = RoutingSecretProvider(DictSecretProvider(ENV), store)  # type: ignore[assignment]  # troca o falso por roteador, mesmo contrato
    return rig


def by_id(report: Any) -> dict[str, Any]:
    return {check.id: check for check in report.checks}


def test_preflight_passes_when_the_vault_has_the_password_and_logs_in_with_it() -> None:
    rig = rig_with(InMemoryCredentialStore({VAULT_NAME: PASSWORD}))

    report = rig.preflight().execute("agenda")

    assert report.ready is True
    login = [r for r in rig.target.requests if r.operation_id == "auth.login"]
    assert len(login) == 1


def test_preflight_missing_vault_secret_names_the_command_but_not_the_value() -> None:
    rig = rig_with(InMemoryCredentialStore())

    report = rig.preflight().execute("agenda")

    check = by_id(report)["secrets:user_a"]
    assert check.ok is False
    assert "user_a.password" in check.detail
    assert "hdast secret set" in (check.operator_detail or "")
    assert f"hdast secret set {VAULT_NAME}" in (check.operator_detail or "")
    dumped = json.dumps(report.model_dump(mode="json"))
    assert VAULT_NAME not in dumped
    assert "operator_detail" not in dumped
    assert all(r.operation_id != "auth.login" for r in rig.target.requests)


def test_preflight_with_a_broken_vault_fails_that_check_with_the_hint_and_does_not_abort() -> None:
    rig = rig_with(InMemoryCredentialStore(broken=True))

    report = rig.preflight().execute("agenda")

    check = by_id(report)["secrets:user_a"]
    assert check.ok is False
    assert "env:NOME" in check.detail
    assert "zap" in by_id(report)
    assert all(r.operation_id != "auth.login" for r in rig.target.requests)


def test_vault_value_is_registered_for_masking_after_preflight() -> None:
    rig = rig_with(InMemoryCredentialStore({VAULT_NAME: PASSWORD}))

    rig.preflight().execute("agenda")

    assert rig.vault.mask(f"corpo com {PASSWORD}") == f"corpo com {MASK}"


def test_probe_with_a_vault_password_leaves_no_trace_of_it_in_any_artifact() -> None:
    rig = rig_with(InMemoryCredentialStore({VAULT_NAME: PASSWORD}))

    result = rig.probe().execute(ProbeRequest(product="agenda"))

    assert result is not None
    stored = rig.store.serialized()
    assert PASSWORD not in stored
    assert TOKEN not in stored
    assert rig.vault.mask(PASSWORD) == MASK


class DoctorSetup:
    def __init__(self, tmp_path: Path, store: InMemoryCredentialStore) -> None:
        host = FakeHost()
        host.directories.add(Path("/produtos"))
        profiles = InMemoryProfileRepository()
        profiles.add(keyring_profile(), existing_files={"./openapi.json"})
        clock = ManualClock()
        self.doctor = Doctor(
            host=host,
            images=host.stack_images(),
            profiles=profiles,
            validator=ValidateProfile(profiles, clock, InMemoryApprovalStore()),
            secrets=RoutingSecretProvider(DictSecretProvider({"ACME_USER_A_LOGIN": LOGIN}), store),
            vault=SecretRegistry(),
            states=InMemoryStackState(tmp_path),
            clock=clock,
            environ={},
            python_version=(3, 12, 4),
            products_dir=Path("/produtos"),
        )


def test_doctor_reports_missing_vault_secret_with_the_command_and_no_value(tmp_path: Path) -> None:
    report = DoctorSetup(tmp_path, InMemoryCredentialStore()).doctor.execute("agenda")

    check = by_id(report)["secrets:user_a"]
    assert check.status == "fail"
    assert f"hdast secret set {VAULT_NAME}" in (check.operator_detail or "")
    assert VAULT_NAME not in json.dumps(report.model_dump(mode="json"))


def test_doctor_is_ok_when_the_vault_has_the_secret_and_never_leaks_it(tmp_path: Path) -> None:
    report = DoctorSetup(tmp_path, InMemoryCredentialStore({VAULT_NAME: PASSWORD})).doctor.execute(
        "agenda"
    )

    assert by_id(report)["secrets:user_a"].status == "ok"
    assert PASSWORD not in json.dumps(report.model_dump(mode="json"))


def test_doctor_with_a_broken_vault_fails_the_check_and_keeps_going(tmp_path: Path) -> None:
    report = DoctorSetup(tmp_path, InMemoryCredentialStore(broken=True)).doctor.execute("agenda")

    check = by_id(report)["secrets:user_a"]
    assert check.status == "fail"
    assert "env:NOME" in check.detail
    assert "profile" in by_id(report)
    assert report.ready is False
