"""Armazém de aprovações em arquivos: gravação atômica e leitura que falha fechada (ADR 0037)."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.storage.approval_store import (
    APPROVALS_DIR,
    MAX_APPROVAL_BYTES,
    FileApprovalStore,
)
from harness_dast.domain.errors import ConfigError, ScopeNotApproved
from tests.fakes.approvals import approval_for
from tests.fakes.profile_data import valid_profile


@pytest.fixture
def store(tmp_path: Path) -> FileApprovalStore:
    return FileApprovalStore(tmp_path / "estado")


def file_of(store: FileApprovalStore, product: str = "demo") -> Path:
    return store.location(product)


def test_read_returns_none_when_the_product_was_never_approved(store: FileApprovalStore) -> None:
    assert store.read("demo") is None


def test_write_then_read_round_trips_the_approval(store: FileApprovalStore) -> None:
    approval = approval_for(valid_profile())

    store.write(approval)

    assert store.read("demo") == approval


def test_the_approval_lives_under_the_approvals_folder_of_the_state_dir(
    store: FileApprovalStore, tmp_path: Path
) -> None:
    store.write(approval_for(valid_profile()))

    assert file_of(store) == tmp_path / "estado" / APPROVALS_DIR / "demo.json"
    assert file_of(store).is_file()


def test_file_holds_the_readable_summary_and_no_secret_value(store: FileApprovalStore) -> None:
    store.write(approval_for(valid_profile()))

    text = file_of(store).read_text(encoding="utf-8")

    assert "Pode alcançar" in text
    assert "env:ACME_USER_A_SENHA" in text  # só o NOME da variável, como no perfil


def test_write_replaces_the_previous_approval_and_leaves_no_temporary_file(
    store: FileApprovalStore,
) -> None:
    first = approval_for(valid_profile())
    store.write(first)
    changed = valid_profile()
    second = approval_for(changed).model_copy(update={"approved_at": "2026-11-15T00:00:00+00:00"})

    store.write(second)

    assert store.read("demo") == second
    assert [p.name for p in file_of(store).parent.iterdir()] == ["demo.json"]


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"   ",
        b"{",
        b"[]",
        b"null",
        b'{"schema_version": 1}',
        b"\xff\xfe\x00not-utf8",
    ],
    ids=["vazio", "espaços", "json-cortado", "lista", "null", "campos-faltando", "não-utf8"],
)
def test_corrupted_or_malformed_file_is_invalid_not_a_crash(
    store: FileApprovalStore, content: bytes
) -> None:
    store.write(approval_for(valid_profile()))
    file_of(store).write_bytes(content)

    with pytest.raises(ScopeNotApproved) as caught:
        store.read("demo")

    assert caught.value.state == "invalid"
    assert caught.value.code == "SCOPE_NOT_APPROVED"


def test_file_of_another_product_is_invalid(store: FileApprovalStore) -> None:
    store.write(approval_for(valid_profile("outro")))
    file_of(store, "demo").write_bytes(file_of(store, "outro").read_bytes())

    with pytest.raises(ScopeNotApproved) as caught:
        store.read("demo")

    assert caught.value.state == "invalid"


def test_file_with_an_unknown_schema_version_is_invalid(store: FileApprovalStore) -> None:
    store.write(approval_for(valid_profile()))
    data = json.loads(file_of(store).read_text(encoding="utf-8"))
    data["schema_version"] = 2
    file_of(store).write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ScopeNotApproved):
        store.read("demo")


def test_file_with_a_hand_edited_digest_is_invalid(store: FileApprovalStore) -> None:
    store.write(approval_for(valid_profile()))
    data = json.loads(file_of(store).read_text(encoding="utf-8"))
    data["blocks"]["limits"] = "c" * 64
    file_of(store).write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ScopeNotApproved):
        store.read("demo")


def test_file_bigger_than_the_cap_is_invalid(store: FileApprovalStore) -> None:
    store.write(approval_for(valid_profile()))
    file_of(store).write_bytes(b" " * (MAX_APPROVAL_BYTES + 1))

    with pytest.raises(ScopeNotApproved):
        store.read("demo")


def test_a_directory_where_the_file_should_be_is_invalid(store: FileApprovalStore) -> None:
    file_of(store).mkdir(parents=True)

    with pytest.raises(ScopeNotApproved):
        store.read("demo")


def test_error_message_never_repeats_the_file_content(store: FileApprovalStore) -> None:
    store.write(approval_for(valid_profile()))
    file_of(store).write_text("SEGREDO-NO-ARQUIVO-123", encoding="utf-8")

    with pytest.raises(ScopeNotApproved) as caught:
        store.read("demo")

    assert "SEGREDO-NO-ARQUIVO-123" not in caught.value.message
    assert "SEGREDO-NO-ARQUIVO-123" not in (caught.value.hint or "")


@pytest.mark.parametrize("name", ["", "../x", "a/b", "A", "x" * 41, "con\\x", "a b"])
def test_product_name_that_is_not_a_slug_never_becomes_a_path(
    store: FileApprovalStore, name: str
) -> None:
    with pytest.raises(ConfigError):
        store.read(name)
    with pytest.raises(ConfigError):
        store.location(name)


def test_write_failure_is_a_config_error_with_a_hint(tmp_path: Path) -> None:
    blocker = tmp_path / "ocupado"
    blocker.write_text("arquivo no lugar da pasta", encoding="utf-8")
    store = FileApprovalStore(blocker)

    with pytest.raises(ConfigError) as caught:
        store.write(approval_for(valid_profile()))

    assert "HDAST_STATE_DIR" in (caught.value.hint or "")
