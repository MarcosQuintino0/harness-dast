"""Cofre do sistema (adaptador `keyring`) com backend de teste em memória."""

import importlib

import pytest
from keyring.backends import fail, null
from keyring.backends.chainer import ChainerBackend

from harness_dast.adapters.secrets import keyring_store
from harness_dast.adapters.secrets.keyring_store import (
    KEYRING_SERVICE,
    KeyringCredentialStore,
    backend_id,
    ensure_system_backend,
)
from harness_dast.cli import secrets_composition
from harness_dast.domain.errors import ExitCode, SecretBackendError
from tests.fakes.credential_store import MemoryBackend


def chainer() -> ChainerBackend:
    return ChainerBackend()  # type: ignore[no-untyped-call]  # construtor do keyring sem anotação


def null_backend() -> null.Keyring:
    return null.Keyring()  # type: ignore[no-untyped-call]  # construtor do keyring sem anotação


SECRET = "valor-do-cofre-LITERAL-9z"  # noqa: S105 - sentinela de teste


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> MemoryBackend:
    instance = MemoryBackend()
    monkeypatch.setattr(
        keyring_store, "ALLOWED_BACKENDS", keyring_store.ALLOWED_BACKENDS | {backend_id(instance)}
    )
    return instance


def test_write_then_read_round_trips_under_the_fixed_service(backend: MemoryBackend) -> None:
    store = KeyringCredentialStore(lambda: backend)

    store.write("AGENDA_SENHA", SECRET)

    assert store.read("AGENDA_SENHA") == SECRET
    assert backend.data == {(KEYRING_SERVICE, "AGENDA_SENHA"): SECRET}


def test_read_returns_none_when_missing_or_empty(backend: MemoryBackend) -> None:
    store = KeyringCredentialStore(lambda: backend)
    backend.data[(KEYRING_SERVICE, "VAZIO")] = ""

    assert store.read("AUSENTE") is None
    assert store.read("VAZIO") is None


def test_remove_reports_whether_it_existed(backend: MemoryBackend) -> None:
    store = KeyringCredentialStore(lambda: backend)
    store.write("A", SECRET)

    assert store.remove("A") is True
    assert store.remove("A") is False
    assert backend.data == {}


def test_backend_is_chosen_only_on_first_use() -> None:
    calls: list[int] = []

    def factory() -> MemoryBackend:
        calls.append(1)
        return MemoryBackend()

    KeyringCredentialStore(factory)

    assert calls == []


@pytest.mark.parametrize("backend_type", [fail.Keyring, null.Keyring, MemoryBackend])
def test_backends_outside_the_system_list_are_refused(backend_type: type) -> None:
    store = KeyringCredentialStore(backend_type)

    with pytest.raises(SecretBackendError) as caught:
        store.read("A")

    assert caught.value.exit_code == ExitCode.PREFLIGHT
    assert caught.value.code == "SECRET_BACKEND_ERROR"
    assert "env:NOME" in (caught.value.hint or "")


def test_chainer_is_accepted_only_when_every_chained_backend_is_allowed(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ChainerBackend, "backends", [backend])
    assert ensure_system_backend(chainer()) is not None

    monkeypatch.setattr(ChainerBackend, "backends", [backend, null_backend()])
    with pytest.raises(SecretBackendError):
        ensure_system_backend(chainer())

    monkeypatch.setattr(ChainerBackend, "backends", [])
    with pytest.raises(SecretBackendError):
        ensure_system_backend(chainer())


def _run(store: KeyringCredentialStore, action: str) -> None:
    if action == "read":
        store.read("A")
    elif action == "write":
        store.write("A", SECRET)
    else:
        store.remove("A")


@pytest.mark.parametrize("action", ["read", "write", "remove"])
def test_backend_failure_becomes_a_clear_error_without_the_value_or_the_cause_message(
    backend: MemoryBackend, action: str
) -> None:
    backend.error = OSError(f"detalhe interno com {SECRET}")
    store = KeyringCredentialStore(lambda: backend)

    with pytest.raises(SecretBackendError) as caught:
        _run(store, action)

    text = f"{caught.value.message} {caught.value.hint}"
    assert "OSError" in text
    assert SECRET not in text
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


def test_factory_failure_becomes_a_clear_error() -> None:
    def factory() -> MemoryBackend:
        raise RuntimeError("PYTHON_KEYRING_BACKEND inválido")

    with pytest.raises(SecretBackendError) as caught:
        KeyringCredentialStore(factory).read("A")

    assert "RuntimeError" in caught.value.message
    assert "PYTHON_KEYRING_BACKEND" not in caught.value.message


def test_the_real_default_backend_is_never_opened_by_the_test_suite() -> None:
    with pytest.raises(AssertionError, match="cofre de credenciais real"):
        secrets_composition.default_backend()


@pytest.mark.parametrize("path", sorted(keyring_store.ALLOWED_BACKENDS))
def test_each_allowed_backend_name_still_exists_in_the_installed_keyring(path: str) -> None:
    module_name, _, class_name = path.rpartition(".")
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        pytest.skip("backend de outro sistema operacional")

    assert hasattr(module, class_name)
