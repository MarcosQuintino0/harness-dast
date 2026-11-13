"""Classe do nome de campo: lista fixa de segredo e dado pessoal."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness_dast.domain.authz_findings import severity_for_fields
from harness_dast.domain.authz_sensitive import classify_field_name


@pytest.mark.parametrize(
    "name",
    [
        "senha",
        "senhaHash",
        "password",
        "passwordHash",
        "password_hash",
        "hash",
        "token",
        "accessToken",
        "refresh_token",
        "secret",
        "clientSecret",
        "apiKey",
        "api_key",
        "api-key",
        "privateKey",
        "segredo",
        "salt",
        "otp",
        "credenciais",
        "cvv",
    ],
)
def test_secret_names_are_secret(name: str) -> None:
    assert classify_field_name(name) == "secret"


@pytest.mark.parametrize(
    "name",
    ["cpf", "cpfPaciente", "CPF", "email", "emailContato", "telefone", "dataNascimento", "rg"],
)
def test_personal_names_are_personal(name: str) -> None:
    assert classify_field_name(name) == "personal"


@pytest.mark.parametrize(
    "name",
    [
        "id",
        "nome",
        "notasInternas",
        "convenioId",
        "origem",
        "merge",
        "hashtag_count_total",
        "pinned",
        "",
        "123",
    ],
)
def test_plain_names_are_plain(name: str) -> None:
    # 'hashtag_count_total' tem a palavra 'hashtag', que não é 'hash': a decisão é por palavra
    assert classify_field_name(name) == "plain"


def test_a_secret_word_wins_over_a_personal_word() -> None:
    assert classify_field_name("emailToken") == "secret"


@given(st.text(max_size=80))
def test_classification_never_raises_and_returns_a_known_class(name: str) -> None:
    assert classify_field_name(name) in {"secret", "personal", "plain"}


def test_exposure_severity_is_medium_for_plain_names() -> None:
    assert severity_for_fields(("items[].notasInternas",)) == "medium"


def test_exposure_severity_is_high_when_any_name_is_secret_or_personal() -> None:
    assert severity_for_fields(("a.nome", "items[].senhaHash")) == "high"
    assert severity_for_fields(("items[].cpf",)) == "high"
