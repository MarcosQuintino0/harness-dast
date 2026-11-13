"""Caso de uso `secret`: gravar e remover só em terminal, listar só nomes e presença."""

import json
from typing import Any

import pytest

from harness_dast.application.secret_admin import SecretAdmin
from harness_dast.domain.errors import ConfigError, SecretBackendError
from harness_dast.observability.logging import SecretRegistry
from tests.fakes.credential_store import InMemoryCredentialStore
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.rig import agenda_profile, profile_data

VALUE = "valor-digitado-pela-pessoa-7Q"


class ScriptedPrompt:
    def __init__(self, value: str = VALUE, *, confirms: bool = True) -> None:
        self.value = value
        self.confirms = confirms
        self.asked: list[str] = []

    def read_value(self, name: str) -> str:
        self.asked.append(f"valor:{name}")
        return self.value

    def confirm_removal(self, name: str) -> bool:
        self.asked.append(f"remover:{name}")
        return self.confirms


def keyring_profile() -> Any:
    auth = profile_data()["auth"]
    first = auth["accounts"][0]
    first["password"] = {"secret_ref": "keyring:ACME_USER_A_SENHA"}
    second = {
        **first,
        "alias": "user_b",
        "username": {"secret_ref": "env:ACME_USER_B_LOGIN"},
        "password": {"secret_ref": "keyring:ACME_USER_B_SENHA"},
    }
    auth["accounts"] = [first, second]
    return agenda_profile(auth=auth)


class Setup:
    def __init__(
        self, store: InMemoryCredentialStore | None = None, prompt: ScriptedPrompt | None = None
    ) -> None:
        self.store = store or InMemoryCredentialStore()
        self.prompt = prompt or ScriptedPrompt()
        self.vault = SecretRegistry()
        self.profiles = InMemoryProfileRepository()
        self.profiles.add(keyring_profile(), existing_files={"./openapi.json"})
        self.admin = SecretAdmin(self.profiles, self.store, self.prompt, self.vault)


def test_set_stores_the_typed_value_and_reports_only_the_name() -> None:
    setup = Setup()

    report = setup.admin.set_secret("ACME_USER_A_SENHA", interactive=True)

    assert setup.store.values == {"ACME_USER_A_SENHA": VALUE}
    assert report.model_dump() == {"name": "ACME_USER_A_SENHA", "replaced": False}
    assert VALUE not in report.model_dump_json()


def test_set_over_an_existing_value_reports_replaced() -> None:
    setup = Setup(InMemoryCredentialStore({"ACME_USER_A_SENHA": "antigo"}))

    report = setup.admin.set_secret("ACME_USER_A_SENHA", interactive=True)

    assert report.replaced is True
    assert setup.store.values["ACME_USER_A_SENHA"] == VALUE


def test_set_registers_the_typed_value_for_masking() -> None:
    setup = Setup()

    setup.admin.set_secret("ACME_USER_A_SENHA", interactive=True)

    assert VALUE not in setup.vault.mask(f"erro com {VALUE}")


def test_set_without_a_terminal_refuses_and_never_prompts_or_writes() -> None:
    setup = Setup()

    with pytest.raises(ConfigError) as caught:
        setup.admin.set_secret("ACME_USER_A_SENHA", interactive=False)

    assert "terminal interativo" in caught.value.message
    assert setup.prompt.asked == []
    assert setup.store.values == {}


@pytest.mark.parametrize("value", ["", "   ", "\n"])
def test_set_with_an_empty_value_refuses_and_writes_nothing(value: str) -> None:
    setup = Setup(prompt=ScriptedPrompt(value))

    with pytest.raises(ConfigError, match="vazio"):
        setup.admin.set_secret("ACME_USER_A_SENHA", interactive=True)

    assert setup.store.values == {}


@pytest.mark.parametrize("name", ["", "minusculo", "HDAST_ZAP_KEY", "A B", "env:A", "1A"])
def test_set_and_delete_refuse_an_invalid_name_before_anything_else(name: str) -> None:
    setup = Setup()

    with pytest.raises(ConfigError, match="Nome de segredo inválido"):
        setup.admin.set_secret(name, interactive=True)
    with pytest.raises(ConfigError, match="Nome de segredo inválido"):
        setup.admin.delete_secret(name, interactive=True)

    assert setup.prompt.asked == []


def test_delete_removes_after_the_person_confirms() -> None:
    setup = Setup(InMemoryCredentialStore({"ACME_USER_A_SENHA": VALUE}))

    report = setup.admin.delete_secret("ACME_USER_A_SENHA", interactive=True)

    assert (report.removed, report.existed) == (True, True)
    assert setup.store.values == {}


def test_delete_keeps_the_value_when_the_person_does_not_confirm() -> None:
    setup = Setup(
        InMemoryCredentialStore({"ACME_USER_A_SENHA": VALUE}), ScriptedPrompt(confirms=False)
    )

    report = setup.admin.delete_secret("ACME_USER_A_SENHA", interactive=True)

    assert (report.removed, report.existed) == (False, True)
    assert setup.store.values == {"ACME_USER_A_SENHA": VALUE}


def test_delete_of_a_missing_name_does_not_prompt() -> None:
    setup = Setup()

    report = setup.admin.delete_secret("ACME_USER_A_SENHA", interactive=True)

    assert (report.removed, report.existed) == (False, False)
    assert setup.prompt.asked == []


def test_delete_without_a_terminal_refuses_and_keeps_the_value() -> None:
    setup = Setup(InMemoryCredentialStore({"ACME_USER_A_SENHA": VALUE}))

    with pytest.raises(ConfigError, match="terminal interativo"):
        setup.admin.delete_secret("ACME_USER_A_SENHA", interactive=False)

    assert setup.store.values == {"ACME_USER_A_SENHA": VALUE}
    assert setup.prompt.asked == []


def test_list_shows_names_fields_and_presence_but_never_the_value() -> None:
    setup = Setup(InMemoryCredentialStore({"ACME_USER_A_SENHA": VALUE}))

    report = setup.admin.list_secrets("agenda")

    entries = {e.name: e for e in report.entries}
    assert set(entries) == {"ACME_USER_A_SENHA", "ACME_USER_B_SENHA"}
    assert entries["ACME_USER_A_SENHA"].present is True
    assert entries["ACME_USER_B_SENHA"].present is False
    assert entries["ACME_USER_A_SENHA"].used_by == ("auth.accounts[user_a].password",)
    assert VALUE not in json.dumps(report.model_dump(mode="json"))


def test_list_ignores_env_references_and_does_not_open_the_vault() -> None:
    store = InMemoryCredentialStore(broken=True)
    setup = Setup(store)
    setup.profiles.add(agenda_profile(), existing_files={"./openapi.json"})

    report = setup.admin.list_secrets("agenda")

    assert report.entries == ()


def test_list_reports_a_broken_vault_as_a_clear_error() -> None:
    setup = Setup(InMemoryCredentialStore(broken=True))

    with pytest.raises(SecretBackendError):
        setup.admin.list_secrets("agenda")
