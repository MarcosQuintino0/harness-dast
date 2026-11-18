"""Caso de uso `hdast setup`: senhas que faltam, resumo com avisos e aprovação (ADR 0114)."""

import copy
from typing import Any

import pytest

from harness_dast.application.scope_approval import ScopeApprovals
from harness_dast.application.secret_admin import SecretAdmin
from harness_dast.application.setup_product import SetupProduct
from harness_dast.application.validate_profile import ValidateProfile
from harness_dast.domain.errors import ConfigError, SecretBackendError
from harness_dast.domain.profile import ProductProfile
from harness_dast.observability.logging import SecretRegistry
from tests.fakes.approvals import APPROVED_AT, InMemoryApprovalStore, ScriptedApprovalPrompt
from tests.fakes.clock import FixedClock
from tests.fakes.credential_store import InMemoryCredentialStore
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.profile_repository import InMemoryProfileRepository

VALUE = "valor-digitado-pela-pessoa-7Q"


class ScriptedSecretPrompt:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def read_value(self, name: str) -> str:
        self.asked.append(name)
        return VALUE

    def confirm_removal(self, name: str) -> bool:
        raise AssertionError("setup nunca remove segredo")


class FakeDefaults:
    def __init__(self, applied: tuple[str, ...] = ()) -> None:
        self.applied = applied

    def read(self, product: str) -> tuple[str, ...]:
        return self.applied


class Notices:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def say(self, text: str) -> None:
        self.lines.append(text)


def keyring_data() -> dict[str, Any]:
    data = copy.deepcopy(valid_profile_data())
    first = data["auth"]["accounts"][0]
    first["password"] = {"secret_ref": "keyring:ACME_USER_A_SENHA"}
    second = {
        **first,
        "alias": "user_b",
        "username": {"secret_ref": "env:ACME_USER_B_LOGIN"},
        "password": {"secret_ref": "keyring:ACME_USER_B_SENHA"},
    }
    data["auth"]["accounts"] = [first, second]
    return data


class Rig:
    def __init__(
        self,
        data: dict[str, Any] | None = None,
        *,
        store: InMemoryCredentialStore | None = None,
        answer: bool = True,
        defaults: tuple[str, ...] = (),
        files: set[str] | None = None,
    ) -> None:
        self.profiles = InMemoryProfileRepository()
        profile = ProductProfile.from_data(data or keyring_data())
        self.profiles.add(profile, existing_files={"./openapi.json"} if files is None else files)
        self.store = store or InMemoryCredentialStore()
        self.secret_prompt = ScriptedSecretPrompt()
        self.approval_store = InMemoryApprovalStore()
        self.approval_prompt = ScriptedApprovalPrompt(answer)
        self.notices = Notices()
        clock = FixedClock(APPROVED_AT)
        self.use_case = SetupProduct(
            validator=ValidateProfile(self.profiles, clock, self.approval_store),
            profiles=self.profiles,
            secrets=SecretAdmin(self.profiles, self.store, self.secret_prompt, SecretRegistry()),
            approvals=ScopeApprovals(
                self.profiles, self.approval_store, self.approval_prompt, clock
            ),
            defaults=FakeDefaults(defaults),
            notifier=self.notices,
        )


def test_run_refuses_without_a_terminal_before_touching_anything() -> None:
    rig = Rig()

    with pytest.raises(ConfigError, match="Só uma pessoa"):
        rig.use_case.run("demo", interactive=False)

    assert rig.secret_prompt.asked == []
    assert rig.approval_prompt.shown == []
    assert rig.store.values == {}
    assert rig.approval_store.items == {}


def test_run_stops_on_an_invalid_profile_before_asking_for_any_password() -> None:
    rig = Rig(files=set())

    with pytest.raises(ConfigError, match=r"FILE_MISSING"):
        rig.use_case.run("demo", interactive=True)

    assert rig.secret_prompt.asked == []
    assert rig.store.values == {}
    assert rig.approval_prompt.shown == []


def test_run_stops_on_a_placeholder_profile_and_lists_each_issue() -> None:
    data = keyring_data()
    data["auth"]["accounts"][0]["username"] = {"secret_ref": "env:MEU_PRODUTO_USUARIO"}
    rig = Rig(data)

    with pytest.raises(ConfigError) as caught:
        rig.use_case.run("demo", interactive=True)

    assert "PLACEHOLDER_SECRET_REF" in caught.value.message
    assert rig.secret_prompt.asked == []


def test_run_raises_when_the_product_does_not_exist() -> None:
    rig = Rig()

    with pytest.raises(ConfigError, match="não existe"):
        rig.use_case.run("outro", interactive=True)


def test_run_asks_only_for_the_missing_passwords_and_writes_them() -> None:
    rig = Rig(store=InMemoryCredentialStore({"ACME_USER_A_SENHA": "ja-existe"}))

    report = rig.use_case.run("demo", interactive=True)

    assert rig.secret_prompt.asked == ["ACME_USER_B_SENHA"]
    assert rig.store.values == {"ACME_USER_A_SENHA": "ja-existe", "ACME_USER_B_SENHA": VALUE}
    assert report.secrets_written == ("ACME_USER_B_SENHA",)
    assert report.secrets_present == ("ACME_USER_A_SENHA",)


def test_run_does_not_ask_again_when_every_password_exists() -> None:
    store = InMemoryCredentialStore({"ACME_USER_A_SENHA": "a", "ACME_USER_B_SENHA": "b"})
    rig = Rig(store=store)

    report = rig.use_case.run("demo", interactive=True)

    assert rig.secret_prompt.asked == []
    assert report.secrets_written == ()
    assert report.secrets_present == ("ACME_USER_A_SENHA", "ACME_USER_B_SENHA")


def test_run_lists_env_secrets_without_asking_for_them() -> None:
    rig = Rig()

    report = rig.use_case.run("demo", interactive=True)

    assert "ACME_USER_A_LOGIN" in report.env_secrets
    assert "ACME_USER_A_LOGIN" not in rig.store.values
    assert any("ambiente" in line and "ACME_USER_A_LOGIN" in line for line in rig.notices.lines)


def test_run_never_shows_or_reports_the_typed_value() -> None:
    rig = Rig()

    report = rig.use_case.run("demo", interactive=True)

    assert VALUE not in report.model_dump_json()
    assert all(VALUE not in line for line in rig.notices.lines)
    assert all(VALUE not in line for _, summary, _ in rig.approval_prompt.shown for line in summary)


def test_run_approves_after_the_person_confirms_and_stores_the_plain_summary() -> None:
    rig = Rig()

    report = rig.use_case.run("demo", interactive=True)

    assert report.approval.approved
    assert "demo" in rig.approval_store.items
    stored = rig.approval_store.items["demo"].summary
    assert not any("PADRÃO MÍNIMO" in line for line in stored)


def test_run_does_not_approve_when_the_person_does_not_confirm() -> None:
    rig = Rig(answer=False)

    report = rig.use_case.run("demo", interactive=True)

    assert not report.approval.approved
    assert rig.approval_store.items == {}
    assert rig.store.values["ACME_USER_B_SENHA"] == VALUE


def test_run_shows_the_minimum_defaults_before_the_summary() -> None:
    rig = Rig(defaults=("limits.requests_per_second = 1",))

    report = rig.use_case.run("demo", interactive=True)

    shown = rig.approval_prompt.shown[0][1]
    assert shown[0].startswith("PADRÃO MÍNIMO DA CLI")
    assert "  - limits.requests_per_second = 1" in shown
    assert shown.index("  - limits.requests_per_second = 1") < shown.index("Produto: demo")
    assert report.defaults == ("limits.requests_per_second = 1",)


def test_run_highlights_an_empty_deny_paths() -> None:
    data = keyring_data()
    data["scope"]["deny_paths"] = []
    rig = Rig(data)

    rig.use_case.run("demo", interactive=True)

    shown = rig.approval_prompt.shown[0][1]
    assert shown[0].startswith("ATENÇÃO: nenhum caminho proibido")


def test_run_shows_no_highlight_when_there_is_nothing_to_warn() -> None:
    rig = Rig()

    rig.use_case.run("demo", interactive=True)

    assert rig.approval_prompt.shown[0][1][0] == "Produto: demo"


def test_run_reports_an_already_approved_profile_without_asking_again() -> None:
    rig = Rig()
    rig.use_case.run("demo", interactive=True)
    rig.approval_prompt.shown.clear()

    report = rig.use_case.run("demo", interactive=True)

    assert report.approval.already_approved
    assert rig.approval_prompt.shown == []


def test_run_accepts_a_closed_window_because_approval_does_not_depend_on_it() -> None:
    data = keyring_data()
    data["scope"]["windows"] = ["seg-dom 00:00-00:01 UTC"]
    rig = Rig(data)

    report = rig.use_case.run("demo", interactive=True)

    assert report.approval.approved


def test_run_stops_when_the_vault_is_unavailable_and_does_not_approve() -> None:
    rig = Rig(store=InMemoryCredentialStore(broken=True))

    with pytest.raises(SecretBackendError):
        rig.use_case.run("demo", interactive=True)

    assert rig.approval_store.items == {}
    assert rig.approval_prompt.shown == []
