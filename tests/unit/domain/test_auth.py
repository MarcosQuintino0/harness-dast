import pytest
from pydantic import TypeAdapter, ValidationError

from harness_dast.domain.auth import ApiKeyAuth, AuthConfig, PasswordLoginAuth

ADAPTER: TypeAdapter[PasswordLoginAuth | ApiKeyAuth] = TypeAdapter(AuthConfig)


def login_data(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "type": "login_password",
        "token_path": "/auth/token",
        "accounts": [
            {
                "alias": "user_a",
                "role": "paciente",
                "username": {"secret_ref": "env:A_LOGIN"},
                "password": {"secret_ref": "env:A_SENHA"},
            }
        ],
    }
    data.update(changes)
    return data


def api_key_data(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "type": "api_key",
        "header_name": "X-API-Key",
        "accounts": [{"alias": "svc", "role": "servico", "api_key": {"secret_ref": "env:SVC_KEY"}}],
    }
    data.update(changes)
    return data


def test_union_builds_login_auth_when_type_is_login_password() -> None:
    auth = ADAPTER.validate_python(login_data())

    assert isinstance(auth, PasswordLoginAuth)
    assert auth.token_header == "Authorization"  # noqa: S105 - nome de cabeçalho
    assert auth.token_scheme == "Bearer"  # noqa: S105 - esquema do cabeçalho
    assert auth.token_response_field == "access_token"  # noqa: S105 - nome de campo


def test_union_builds_api_key_auth_when_type_is_api_key() -> None:
    auth = ADAPTER.validate_python(api_key_data())

    assert isinstance(auth, ApiKeyAuth)
    assert auth.accounts[0].api_key.env_name == "SVC_KEY"


def test_login_expresses_custom_token_location_and_header_when_configured() -> None:
    auth = PasswordLoginAuth.model_validate(
        login_data(
            request_encoding="json",
            username_field="user",
            password_field="pass",  # noqa: S106 - nome do campo, não um segredo
            token_response_field="data.token",  # noqa: S106 - nome de campo
            token_header="X-Auth-Token",  # noqa: S106 - nome de cabeçalho
            token_scheme="",
        )
    )

    assert (auth.request_encoding, auth.token_response_field, auth.token_header) == (
        "json",
        "data.token",
        "X-Auth-Token",
    )
    assert auth.token_scheme == ""


@pytest.mark.parametrize("auth_type", ["client_credentials", "form_login", "sso", "", None, 1])
def test_union_rejects_type_when_it_is_not_one_of_the_two_v1_types(auth_type: object) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(login_data(type=auth_type))


def test_union_rejects_when_type_is_missing() -> None:
    data = login_data()
    del data["type"]

    with pytest.raises(ValidationError):
        ADAPTER.validate_python(data)


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"token_path": "auth/token"}, id="path_without_slash"),
        pytest.param({"token_path": "/auth/*"}, id="path_with_wildcard"),
        pytest.param({"token_path": "/auth/../x"}, id="path_with_dotdot"),
        pytest.param({"token_path": "/auth/token?x=1"}, id="path_with_query"),
        pytest.param({"token_path": ""}, id="empty_path"),
        pytest.param({"accounts": []}, id="no_accounts"),
        pytest.param({"request_encoding": "xml"}, id="unknown_encoding"),
        pytest.param({"username_field": "a b"}, id="space_in_username_field"),
        pytest.param({"password_field": ""}, id="empty_password_field"),
        pytest.param({"token_response_field": "a..b"}, id="bad_response_path"),
        pytest.param({"token_response_field": "$.token"}, id="jsonpath_not_supported"),
        pytest.param({"token_header": "Host"}, id="reserved_header"),
        pytest.param({"token_header": "Content-Length"}, id="reserved_header_content_length"),
        pytest.param({"token_header": "X Auth"}, id="header_with_space"),
        pytest.param({"token_header": "X-Auth\r\nX: y"}, id="header_injection"),
        pytest.param({"token_scheme": "Bearer token"}, id="scheme_with_space"),
        pytest.param({"unknown": 1}, id="extra_field"),
    ],
)
def test_login_rejects_when_field_is_invalid(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PasswordLoginAuth.model_validate(login_data(**changes))


def test_login_rejects_when_aliases_repeat() -> None:
    account = login_data()["accounts"]
    assert isinstance(account, list)

    with pytest.raises(ValidationError, match="repetidos"):
        PasswordLoginAuth.model_validate(login_data(accounts=[account[0], account[0]]))


def test_api_key_rejects_when_aliases_repeat() -> None:
    account = api_key_data()["accounts"]
    assert isinstance(account, list)

    with pytest.raises(ValidationError, match="repetidos"):
        ApiKeyAuth.model_validate(api_key_data(accounts=[account[0], account[0]]))


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"header_name": "Host"}, id="reserved_header"),
        pytest.param({"header_name": "Transfer-Encoding"}, id="reserved_transfer_encoding"),
        pytest.param({"header_name": ""}, id="empty_header"),
        pytest.param({"header_name": "X_API_KEY"}, id="underscore_header"),
        pytest.param({"accounts": []}, id="no_accounts"),
        pytest.param({"token_path": "/x"}, id="field_from_other_type"),
    ],
)
def test_api_key_rejects_when_field_is_invalid(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ApiKeyAuth.model_validate(api_key_data(**changes))


@pytest.mark.parametrize(
    "account",
    [
        pytest.param({"alias": "User A", "role": "r"}, id="alias_with_space_and_uppercase"),
        pytest.param({"alias": "1abc", "role": "r"}, id="alias_starting_with_digit"),
        pytest.param({"alias": "a" * 33, "role": "r"}, id="alias_too_long"),
        pytest.param({"alias": "", "role": "r"}, id="empty_alias"),
        pytest.param({"alias": "user_a", "role": ""}, id="empty_role"),
        pytest.param({"alias": "user_a", "role": "   "}, id="blank_role"),
        pytest.param({"alias": "user_a", "role": "a\x00b"}, id="role_with_control_char"),
        pytest.param({"alias": "user_a"}, id="missing_role"),
        pytest.param({"role": "r"}, id="missing_alias"),
    ],
)
def test_account_rejects_when_alias_or_role_is_invalid(account: dict[str, object]) -> None:
    full = {"api_key": {"secret_ref": "env:K"}, **account}

    with pytest.raises(ValidationError):
        ApiKeyAuth.model_validate(api_key_data(accounts=[full]))


@pytest.mark.parametrize(
    "secret_field",
    [
        pytest.param({"username": "joao"}, id="literal_username"),
        pytest.param({"password": "hunter2"}, id="literal_password"),
        pytest.param({"password": {"secret_ref": "hunter2"}}, id="literal_inside_secret_ref"),
        pytest.param({"password": {"value": "hunter2"}}, id="wrong_key"),
        pytest.param({"password": None}, id="null_password"),
    ],
)
def test_login_account_rejects_literal_secret_when_reference_is_expected(
    secret_field: dict[str, object],
) -> None:
    account = {
        "alias": "user_a",
        "role": "paciente",
        "username": {"secret_ref": "env:U"},
        "password": {"secret_ref": "env:P"},
        **secret_field,
    }

    with pytest.raises(ValidationError):
        PasswordLoginAuth.model_validate(login_data(accounts=[account]))
