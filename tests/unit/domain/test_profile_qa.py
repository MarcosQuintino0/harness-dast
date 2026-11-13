"""Testes independentes (QA) da validação de perfil, a partir de dicionários."""

# ruff: noqa: S105, S104, S603, RUF001, RUF100, PT011, TRY301

import copy
from datetime import UTC, datetime
from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope import OutboundRequest

SECRET = "hunter2-S3GR3D0-LITERAL"


def valid() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "product": "agenda",
        "environment": {"name": "homolog", "base_url": "https://agenda.hml.example.com"},
        "openapi": "./openapi.json",
        "scope": {
            "allow": [
                {
                    "host": "agenda.hml.example.com",
                    "paths": ["/api/**", "/auth/token"],
                    "methods": ["GET", "POST"],
                }
            ],
            "deny_paths": ["/api/admin/**"],
            "authorization": {"reference": "SEC-1", "valid_until": "2027-01-31"},
            "windows": ["seg-sex 20:00-06:00 America/Sao_Paulo"],
        },
        "limits": {"requests_per_second": 5, "max_duration_minutes": 60, "zap_threads_per_host": 2},
        "auth": {
            "type": "login_password",
            "token_path": "/auth/token",
            "accounts": [
                {
                    "alias": "user_a",
                    "role": "paciente",
                    "username": {"secret_ref": "env:A_USER"},
                    "password": {"secret_ref": "env:A_PASS"},
                }
            ],
        },
        "cleanup": {
            "type": "oracle_sql",
            "script": "./cleanup/cleanup.sql",
            "connection": {"secret_ref": "env:A_DB"},
            "requires_confirmation": True,
        },
    }


def api_key_auth() -> dict[str, Any]:
    return {
        "type": "api_key",
        "header_name": "X-API-Key",
        "accounts": [{"alias": "svc", "role": "servico", "api_key": {"secret_ref": "env:K"}}],
    }


def with_value(path: list[str | int], value: object) -> dict[str, Any]:
    data = valid()
    cursor: Any = data
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value
    return data


def without(path: list[str | int]) -> dict[str, Any]:
    data = valid()
    cursor: Any = data
    for part in path[:-1]:
        cursor = cursor[part]
    del cursor[path[-1]]
    return data


def error_of(data: object) -> ConfigError:
    with pytest.raises(ConfigError) as caught:
        ProductProfile.from_data(data)
    return caught.value


def test_from_data_builds_profile_when_data_is_valid() -> None:
    profile = ProductProfile.from_data(valid())

    assert profile.product == "agenda"
    assert profile.scope.windows[0].timezone == "America/Sao_Paulo"
    assert profile.cleanup is not None


def test_from_data_accepts_api_key_auth_when_type_is_api_key() -> None:
    data = valid()
    data["auth"] = api_key_auth()

    assert ProductProfile.from_data(data).auth.type == "api_key"


def test_from_data_accepts_profile_without_cleanup() -> None:
    assert ProductProfile.from_data(without(["cleanup"])).cleanup is None


def test_from_data_does_not_mutate_input() -> None:
    data = valid()
    snapshot = copy.deepcopy(data)

    ProductProfile.from_data(data)

    assert data == snapshot


@pytest.mark.parametrize("data", [None, [], "texto", 1, [valid()], (), set()])
def test_from_data_raises_config_error_when_root_is_not_a_mapping(data: object) -> None:
    error_of(data)


@pytest.mark.parametrize("version", [0, 2, -1, "1", 1.0, True, None, [1], {"v": 1}])
def test_from_data_raises_config_error_when_schema_version_is_not_exactly_one(
    version: object,
) -> None:
    message = error_of(with_value(["schema_version"], version)).message

    assert "schema_version" in message


def test_from_data_raises_config_error_when_schema_version_is_missing() -> None:
    assert "schema_version" in error_of(without(["schema_version"])).message


@pytest.mark.parametrize(
    "path",
    [
        ["product"],
        ["environment"],
        ["environment", "name"],
        ["environment", "base_url"],
        ["openapi"],
        ["scope"],
        ["scope", "allow"],
        ["scope", "authorization"],
        ["scope", "authorization", "reference"],
        ["scope", "authorization", "valid_until"],
        ["scope", "windows"],
        ["limits"],
        ["limits", "requests_per_second"],
        ["limits", "max_duration_minutes"],
        ["limits", "zap_threads_per_host"],
        ["auth"],
        ["auth", "type"],
        ["auth", "accounts"],
        ["auth", "token_path"],
        ["scope", "allow", 0, "host"],
        ["scope", "allow", 0, "paths"],
        ["scope", "allow", 0, "methods"],
        ["auth", "accounts", 0, "alias"],
        ["auth", "accounts", 0, "password"],
        ["cleanup", "requires_confirmation"],
        ["cleanup", "connection"],
        ["cleanup", "script"],
    ],
)
def test_from_data_raises_config_error_when_required_field_is_missing(
    path: list[str | int],
) -> None:
    error_of(without(path))


@pytest.mark.parametrize(
    "path",
    [
        [],
        ["environment"],
        ["scope"],
        ["scope", "allow", 0],
        ["scope", "authorization"],
        ["limits"],
        ["auth"],
        ["auth", "accounts", 0],
        ["auth", "accounts", 0, "username"],
        ["cleanup"],
        ["cleanup", "connection"],
    ],
)
def test_from_data_raises_config_error_when_unknown_field_is_present(path: list[str | int]) -> None:
    data = valid()
    cursor: Any = data
    for part in path:
        cursor = cursor[part]
    cursor["campo_inventado"] = SECRET

    message = error_of(data).message

    assert "campo_inventado" in message
    assert SECRET not in message


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["product"], 1),
        (["product"], "Agenda"),
        (["product"], "a b"),
        (["product"], "../x"),
        (["product"], ""),
        (["product"], "a" * 41),
        (["environment", "name"], "PROD UCAO"),
        (["environment", "name"], ""),
        (["environment", "base_url"], "ftp://agenda.hml.example.com"),
        (["environment", "base_url"], "https://agenda.hml.example.com?x=1"),
        (["environment", "base_url"], "https://agenda.hml.example.com#x"),
        (["environment", "base_url"], "https://user@agenda.hml.example.com"),
        (["environment", "base_url"], 5),
        (["openapi"], "/etc/passwd"),
        (["openapi"], "C:/x.json"),
        (["openapi"], "../x.json"),
        (["openapi"], "a/../../x"),
        (["openapi"], "~/x"),
        (["openapi"], "..\\x"),
        (["openapi"], ""),
        (["openapi"], 5),
        (["scope", "allow"], []),
        (["scope", "allow"], "x"),
        (["scope", "windows"], []),
        (["scope", "windows"], ["quando der"]),
        (["scope", "windows"], "seg-sex 20:00-06:00 UTC"),
        (["scope", "authorization", "valid_until"], "ontem"),
        (["scope", "authorization", "reference"], ""),
        (["limits", "requests_per_second"], 0),
        (["limits", "requests_per_second"], -1),
        (["limits", "requests_per_second"], 50.5),
        (["limits", "requests_per_second"], 1000),
        (["limits", "requests_per_second"], float("nan")),
        (["limits", "requests_per_second"], float("inf")),
        (["limits", "requests_per_second"], True),
        (["limits", "requests_per_second"], "5"),
        (["limits", "requests_per_second"], None),
        (["limits", "max_duration_minutes"], 0),
        (["limits", "max_duration_minutes"], -1),
        (["limits", "max_duration_minutes"], 481),
        (["limits", "max_duration_minutes"], True),
        (["limits", "max_duration_minutes"], 5.5),
        (["limits", "max_duration_minutes"], "60"),
        (["limits", "zap_threads_per_host"], 0),
        (["limits", "zap_threads_per_host"], 9),
        (["limits", "zap_threads_per_host"], False),
        (["limits", "zap_threads_per_host"], float("nan")),
        (["cleanup", "type"], "mysql"),
        (["cleanup", "script"], "/abs/x.sql"),
        (["cleanup", "script"], "../x.sql"),
        (["cleanup", "script"], "C:\\x.sql"),
    ],
)
def test_from_data_raises_config_error_when_value_is_invalid(
    path: list[str | int], value: object
) -> None:
    error_of(with_value(path, value))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["limits", "requests_per_second"], 50),
        (["limits", "requests_per_second"], 0.1),
        (["limits", "max_duration_minutes"], 480),
        (["limits", "max_duration_minutes"], 1),
        (["limits", "zap_threads_per_host"], 8),
        (["limits", "zap_threads_per_host"], 1),
    ],
)
def test_from_data_accepts_limits_when_value_is_exactly_at_the_boundary(
    path: list[str | int], value: object
) -> None:
    assert ProductProfile.from_data(with_value(path, value)) is not None


@pytest.mark.parametrize("flag", [False, "false", "true", 0, 1, None, "yes"])
def test_from_data_raises_config_error_when_cleanup_confirmation_is_not_literally_true(
    flag: object,
) -> None:
    error_of(with_value(["cleanup", "requires_confirmation"], flag))


@pytest.mark.parametrize(
    "path",
    [
        ["auth", "accounts", 0, "username"],
        ["auth", "accounts", 0, "password"],
        ["cleanup", "connection"],
    ],
)
@pytest.mark.parametrize(
    "bad",
    [
        SECRET,
        {"secret_ref": SECRET},
        {"secret_ref": f"env:{SECRET}"},
        {"secret_ref": "env:lower"},
        {"secret_ref": "ENV:X"},
        {"secret_ref": "env:"},
        {"secret_ref": "file:/etc/passwd"},
        {"secret_ref": "env:A\nB"},
        {"secret_ref": "env:A B"},
        {"secret_ref": "env:A", "value": SECRET},
        {"value": SECRET},
        [SECRET],
        {"secret_ref": ["env:A"]},
        {"secret_ref": None},
        {"secret_ref": "env:" + "A" * 200},
    ],
)
def test_from_data_never_echoes_secret_when_secret_ref_is_literal_or_malformed(
    path: list[str | int], bad: object
) -> None:
    error = error_of(with_value(path, bad))

    blob = f"{error.message}|{error.hint}|{error!s}|{error!r}"
    assert SECRET not in blob
    assert "hunter2" not in blob


def test_from_data_never_echoes_api_key_literal() -> None:
    data = valid()
    data["auth"] = api_key_auth()
    data["auth"]["accounts"][0]["api_key"] = SECRET

    error = error_of(data)

    assert SECRET not in f"{error.message}{error.hint}{error!r}"


def test_from_data_never_echoes_value_when_wrong_type_holds_a_secret() -> None:
    paths: tuple[list[str | int], ...] = (
        ["limits", "requests_per_second"],
        ["scope", "authorization", "valid_until"],
        ["product"],
        ["environment", "name"],
        ["auth", "accounts", 0, "alias"],
        ["auth", "token_path"],
        ["scope", "windows", 0],
        ["scope", "allow", 0, "methods", 0],
        ["scope", "allow", 0, "paths", 0],
        ["scope", "deny_paths", 0],
        ["cleanup", "type"],
        ["auth", "type"],
        ["schema_version"],
    )
    for path in paths:
        error = error_of(with_value(path, SECRET))
        assert SECRET not in f"{error.message}{error.hint}", path


@pytest.mark.parametrize(
    "host", [f"{SECRET}.example.com", f"a_{SECRET}", f"{SECRET}/x", f"{SECRET}@evil.com"]
)
def test_from_data_never_echoes_value_when_scope_host_is_invalid(host: str) -> None:
    # ProductProfile.from_data promete: "nunca contém os valores informados".
    error = error_of(with_value(["scope", "allow", 0, "host"], host))

    assert SECRET.lower() not in f"{error.message}{error.hint}".lower()


def test_from_data_never_echoes_value_when_environment_base_url_has_invalid_host() -> None:
    error = error_of(with_value(["environment", "base_url"], f"https://{SECRET}_x.com/"))

    assert SECRET.lower() not in f"{error.message}{error.hint}".lower()


def test_from_data_raises_when_account_aliases_are_duplicated() -> None:
    data = valid()
    data["auth"]["accounts"].append(copy.deepcopy(data["auth"]["accounts"][0]))

    assert "repetid" in error_of(data).message


@pytest.mark.parametrize("alias", ["User_A", "1a", "a b", "a-b", "", "a" * 33, "../x", "ü"])
def test_from_data_raises_when_alias_is_malformed(alias: str) -> None:
    error_of(with_value(["auth", "accounts", 0, "alias"], alias))


def test_from_data_raises_when_api_key_accounts_have_duplicated_alias() -> None:
    data = valid()
    data["auth"] = api_key_auth()
    data["auth"]["accounts"].append(copy.deepcopy(data["auth"]["accounts"][0]))

    error_of(data)


@pytest.mark.parametrize(
    "header",
    ["Host", "host", "Content-Length", "Transfer-Encoding", "Connection", "A B", "A:B", "", "X\nY"],
)
def test_from_data_raises_when_token_header_is_reserved_or_malformed(header: str) -> None:
    error_of(with_value(["auth", "token_header"], header))


@pytest.mark.parametrize("header", ["Host", "content-length", "X Y", "X:Y", ""])
def test_from_data_raises_when_api_key_header_is_reserved_or_malformed(header: str) -> None:
    data = valid()
    data["auth"] = api_key_auth()
    data["auth"]["header_name"] = header

    error_of(data)


@pytest.mark.parametrize(
    "token_path", ["/auth/*", "/auth/**", "auth/token", "/a/../b", "", "/a?x=1"]
)
def test_from_data_raises_when_token_path_is_not_a_literal_path(token_path: str) -> None:
    data = with_value(["auth", "token_path"], token_path)

    error_of(data)


def test_from_data_raises_when_base_url_host_is_outside_scope() -> None:
    message = error_of(with_value(["environment", "base_url"], "https://outro.example.com")).message

    assert "scope.allow" in message


@pytest.mark.parametrize(
    "base_url",
    [
        "http://agenda.hml.example.com",
        "https://agenda.hml.example.com:8443",
        "https://AGENDA.hml.example.com.evil.com",
    ],
)
def test_from_data_raises_when_base_url_scheme_or_port_differs_from_rule(base_url: str) -> None:
    error_of(with_value(["environment", "base_url"], base_url))


def test_from_data_raises_when_login_path_is_outside_scope_paths() -> None:
    error_of(with_value(["auth", "token_path"], "/login-fora-do-escopo"))


def test_from_data_raises_when_login_path_is_denied() -> None:
    data = valid()
    data["scope"]["deny_paths"].append("/auth/token")

    error_of(data)


def test_from_data_raises_when_login_method_post_is_not_permitted() -> None:
    error_of(with_value(["scope", "allow", 0, "methods"], ["GET"]))


def test_from_data_uses_base_url_path_prefix_when_checking_login_path() -> None:
    data = with_value(["environment", "base_url"], "https://agenda.hml.example.com/api")
    data["auth"]["token_path"] = "/auth/token"

    # /api/auth/token está coberto por /api/** com POST.
    assert ProductProfile.from_data(data) is not None


def test_from_data_reports_every_problem_in_one_message() -> None:
    data = valid()
    data["product"] = "A B"
    data["limits"]["requests_per_second"] = 0
    data["openapi"] = "../x"

    message = error_of(data).message

    for field in ("product", "limits.requests_per_second", "openapi"):
        assert field in message


def test_from_data_raises_config_error_not_validation_error_when_nested_types_are_wrong() -> None:
    data = valid()
    data["scope"]["allow"][0]["paths"] = "/api/**"
    data["auth"]["accounts"] = {"alias": "x"}
    data["limits"] = [1, 2, 3]

    error_of(data)


def test_from_data_rejects_wildcard_host_and_host_with_port() -> None:
    for host in ("*.example.com", "agenda.hml.example.com:443", "https://agenda.hml.example.com"):
        error_of(with_value(["scope", "allow", 0, "host"], host))


def test_from_data_rejects_local_host_without_allow_local_and_public_with_it() -> None:
    data = valid()
    data["scope"]["allow"][0]["host"] = "localhost"
    data["environment"]["base_url"] = "http://localhost"
    error_of(data)

    data2 = with_value(["scope", "allow", 0, "allow_local"], True)
    error_of(data2)


def test_from_data_rejects_public_ip_literal_even_with_allow_local() -> None:
    data = valid()
    data["scope"]["allow"][0].update({"host": "8.8.8.8", "allow_local": True})
    data["environment"]["base_url"] = "https://8.8.8.8"

    error_of(data)


def test_from_data_accepts_lab_profile_when_local_host_is_explicitly_allowed() -> None:
    data = valid()
    data["scope"]["allow"][0].update(
        {"host": "vampi", "allow_local": True, "scheme": "http", "port": 5000}
    )
    data["environment"]["base_url"] = "http://vampi:5000"

    profile = ProductProfile.from_data(data)

    profile.guard().ensure_allowed(OutboundRequest(method="GET", url="http://vampi:5000/api/x"))
    with pytest.raises(ScopeViolation):
        profile.guard().ensure_allowed(OutboundRequest(method="GET", url="http://vampi/api/x"))


def test_window_given_as_mapping_cannot_have_start_equal_to_end() -> None:
    window = {"days": [0, 1, 2], "start_minute": 600, "end_minute": 600, "timezone": "UTC"}

    error_of(with_value(["scope", "windows"], [window]))


def test_ensure_runnable_checks_authorization_and_window() -> None:
    profile = ProductProfile.from_data(valid())

    profile.ensure_runnable(datetime(2026, 11, 13, 23, 0, tzinfo=UTC))  # sex 20:00 em SP
    with pytest.raises(ScopeViolation):
        profile.ensure_runnable(datetime(2026, 11, 13, 12, 0, tzinfo=UTC))  # sex 09:00 em SP
    with pytest.raises(ScopeViolation):
        profile.ensure_runnable(datetime(2027, 2, 2, 23, 0, tzinfo=UTC))  # autorização vencida
    with pytest.raises(ConfigError):
        profile.ensure_runnable(datetime(2026, 11, 13, 23, 0))


def test_profile_is_immutable() -> None:
    profile = ProductProfile.from_data(valid())

    with pytest.raises(ValueError):
        profile.product = "outro"  # type: ignore[misc]  # prova da imutabilidade


def test_guard_of_profile_does_not_include_window_or_authorization_fields() -> None:
    profile = ProductProfile.from_data(valid())

    assert set(profile.scope.to_scope().model_dump()) == {"allow", "deny_paths"}


def test_from_data_accepts_string_keys_only_and_ignores_nothing() -> None:
    data = valid()
    data[1] = "x"  # type: ignore[index]  # chave não-string vinda de YAML malformado

    error_of(data)
