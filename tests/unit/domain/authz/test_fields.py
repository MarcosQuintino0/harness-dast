"""Classe do nome de um campo para a atribuição em massa (ADR 0040)."""

import pytest

from harness_dast.domain.authz.fields import classify_candidate, is_excluded_name, moves_up


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("role", "privilege"),
        ("isAdmin", "privilege"),
        ("is_admin", "privilege"),
        ("nivelAcesso", "privilege"),
        ("nivel", "privilege"),
        ("Plano", "privilege"),
        ("saldo", "balance"),
        ("creditLimit", "balance"),
        ("preco", "price"),
        ("discount", "price"),
        ("isActive", "state"),
        ("bloqueado", "state"),
        ("ownerId", "ownership"),
        ("tenant_id", "ownership"),
        ("createdBy", "ownership"),
        ("tenantLevel", "ownership"),
        ("nome", None),
        ("", None),
    ],
)
def test_the_name_decides_the_class(name: str, kind: str | None) -> None:
    assert classify_candidate(name) == kind


@pytest.mark.parametrize(
    ("name", "up"),
    [("saldo", True), ("preco", False), ("discount", True), ("blocked", False), ("isActive", True)],
)
def test_the_direction_of_the_test_value_comes_from_the_name(name: str, up: bool) -> None:
    assert moves_up(name) is up


@pytest.mark.parametrize(
    "name",
    ["passwordHash", "apiKey", "id", "uuid", "createdAt", "updated_at", "version", "etag", "now"],
)
def test_secret_identifier_audit_and_volatile_names_are_excluded(name: str) -> None:
    assert is_excluded_name(name, "medicos") is True


def test_the_id_of_the_resource_itself_is_excluded_but_another_id_is_not() -> None:
    assert is_excluded_name("medicoId", "medicos") is True
    assert is_excluded_name("planoId", "medicos") is False
    assert is_excluded_name("medicoId", None) is False


def test_a_short_stem_does_not_exclude_by_prefix() -> None:
    assert is_excluded_name("mId", "medicos") is False
