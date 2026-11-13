"""Campos aditivos do bloco `cleanup` do perfil (schema v1)."""

from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from tests.fakes.cleanup_rig import cleanup_profile
from tests.fakes.profile_data import valid_profile_data


def profile_with(**cleanup: Any) -> ProductProfile:
    data = valid_profile_data("demo", with_cleanup=True)
    data["cleanup"].update(cleanup)
    return ProductProfile.from_data(data)


def test_old_cleanup_block_without_the_new_fields_is_still_valid_but_not_runnable() -> None:
    profile = profile_with()

    assert profile.cleanup is not None
    assert profile.cleanup.missing_for_run() == (
        "cleanup.user",
        "cleanup.password",
        "cleanup.allowed_tables",
        "cleanup.max_rows",
    )


def test_complete_block_has_nothing_missing_and_uppercases_tables_and_schema() -> None:
    profile = cleanup_profile(allowed_tables=["pedido", "app.log"], db_schema="app")

    assert profile.cleanup is not None
    assert profile.cleanup.missing_for_run() == ()
    assert profile.cleanup.allowed_tables == ("PEDIDO", "APP.LOG")
    assert profile.cleanup.db_schema == "APP"


@pytest.mark.parametrize(
    "changes",
    [
        {"allowed_tables": ["a b"]},
        {"allowed_tables": ['"PEDIDO"']},
        {"allowed_tables": ["a.b.c"]},
        {"allowed_tables": ["PEDIDO", "pedido"]},
        {"allowed_tables": ["1TABELA"]},
        {"allowed_tables": "PEDIDO"},
        {"max_rows": 0},
        {"max_rows": -1},
        {"max_rows": 1_000_001},
        {"max_rows": True},
        {"max_rows": "10"},
        {"max_rows": 1.5},
        {"db_schema": "a;b"},
        {"db_schema": "x" * 40},
        {"user": "literal"},
        {"password": {"secret_ref": "senha-literal"}},
        {"desconhecido": 1},
    ],
)
def test_rejects_invalid_new_fields(changes: dict[str, Any]) -> None:
    with pytest.raises(ConfigError):
        profile_with(**changes)


def test_error_for_a_literal_password_does_not_echo_it() -> None:
    with pytest.raises(ConfigError) as caught:
        profile_with(password={"secret_ref": "SenhaLiteral123"})

    assert "SenhaLiteral123" not in caught.value.message
