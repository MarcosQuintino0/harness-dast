import copy
from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from harness_dast.domain.auth import ApiKeyAuth, PasswordLoginAuth
from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.profile import (
    SUPPORTED_SCHEMA_VERSION,
    CleanupConfig,
    ProductProfile,
)
from harness_dast.domain.scope import OutboundRequest

Data = dict[str, object]
LITERAL = "hunter2-SEGREDO-LITERAL"


def valid_data() -> Data:
    return {
        "schema_version": 1,
        "product": "agenda",
        "environment": {"name": "homolog", "base_url": "https://agenda.hml.exemplo.com.br"},
        "openapi": "./openapi.json",
        "scope": {
            "allow": [
                {
                    "host": "agenda.hml.exemplo.com.br",
                    "paths": ["/api/**", "/auth/token"],
                    "methods": ["GET", "POST", "PUT", "PATCH"],
                }
            ],
            "deny_paths": ["/api/notificacoes/**", "/api/conta/excluir"],
            "authorization": {"reference": "SEC-1234", "valid_until": "2027-01-31"},
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
                    "username": {"secret_ref": "env:AGENDA_USER_A_LOGIN"},
                    "password": {"secret_ref": "env:AGENDA_USER_A_SENHA"},
                }
            ],
        },
        "cleanup": {
            "type": "oracle_sql",
            "script": "./cleanup/cleanup.sql",
            "connection": {"secret_ref": "env:AGENDA_ORACLE_LIMPEZA"},
            "requires_confirmation": True,
        },
    }


def mutated(path: str, value: object) -> Data:
    """Cópia do perfil válido com o valor em `path` (ex.: `scope.allow.0.host`) trocado."""
    data = valid_data()
    cursor: object = data
    *parents, last = path.split(".")
    for part in parents:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cast(Data, cursor)[part]
    if isinstance(cursor, list):
        cursor[int(last)] = value
    else:
        cast(Data, cursor)[last] = value
    return data


def removed(path: str) -> Data:
    data = valid_data()
    cursor: object = data
    *parents, last = path.split(".")
    for part in parents:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cast(Data, cursor)[part]
    del cast(Data, cursor)[last]
    return data


def load(data: Data) -> ProductProfile:
    return ProductProfile.from_data(data)


def error_for(data: Data) -> ConfigError:
    with pytest.raises(ConfigError) as caught:
        ProductProfile.from_data(data)
    return caught.value


# ----------------------------------------------------------------------- válido


def test_from_data_builds_profile_when_data_matches_the_design_example() -> None:
    profile = load(valid_data())

    assert profile.product == "agenda"
    assert profile.scope.authorization.reference == "SEC-1234"
    assert profile.limits.requests_per_second == 5
    assert isinstance(profile.auth, PasswordLoginAuth)
    assert profile.auth.accounts[0].username.env_name == "AGENDA_USER_A_LOGIN"
    assert isinstance(profile.cleanup, CleanupConfig)


def test_from_data_accepts_api_key_auth_when_type_is_api_key() -> None:
    data = valid_data()
    data["auth"] = {
        "type": "api_key",
        "header_name": "X-API-Key",
        "accounts": [{"alias": "svc", "role": "servico", "api_key": {"secret_ref": "env:SVC_KEY"}}],
    }

    assert isinstance(load(data).auth, ApiKeyAuth)


def test_from_data_accepts_profile_without_cleanup_when_cleanup_is_omitted() -> None:
    assert load(removed("cleanup")).cleanup is None


def test_from_data_does_not_mutate_input_when_called() -> None:
    data = valid_data()
    snapshot = copy.deepcopy(data)

    load(data)

    assert data == snapshot


def test_profile_is_frozen_when_attribute_assignment_is_attempted() -> None:
    profile = load(valid_data())

    with pytest.raises(ValidationError):
        profile.product = "outro"  # type: ignore[misc]  # prova que o modelo é congelado


def test_profile_guard_enforces_the_profile_scope_when_requests_are_checked() -> None:
    guard = load(valid_data()).guard()

    guard.ensure_allowed(
        OutboundRequest(method="GET", url="https://agenda.hml.exemplo.com.br/api/consultas")
    )
    with pytest.raises(ScopeViolation, match="deny_paths"):
        guard.ensure_allowed(
            OutboundRequest(method="GET", url="https://agenda.hml.exemplo.com.br/api/conta/excluir")
        )


# --------------------------------------------------------------- schema_version


def test_from_data_raises_config_error_when_schema_version_is_missing() -> None:
    error = error_for(removed("schema_version"))

    assert "schema_version" in error.message
    assert error.hint


@pytest.mark.parametrize("version", [0, 2, -1, 99])
def test_from_data_raises_config_error_when_schema_version_is_not_supported(version: int) -> None:
    error = error_for(mutated("schema_version", version))

    assert f"schema_version {version}" in error.message
    assert str(SUPPORTED_SCHEMA_VERSION) in error.message


@pytest.mark.parametrize("version", ["1", 1.0, True, None, [1]])
def test_from_data_raises_config_error_when_schema_version_has_wrong_type(version: object) -> None:
    error = error_for(mutated("schema_version", version))

    assert "schema_version" in error.message


@pytest.mark.parametrize("data", [None, [], "perfil", 42])
def test_from_data_raises_config_error_when_profile_is_not_a_mapping(data: object) -> None:
    with pytest.raises(ConfigError, match="mapa"):
        ProductProfile.from_data(data)


def test_from_data_raises_config_error_when_profile_is_empty() -> None:
    with pytest.raises(ConfigError, match="schema_version"):
        ProductProfile.from_data({})


# ------------------------------------------------------ campos ausentes/extras


@pytest.mark.parametrize(
    "path",
    [
        "product",
        "environment",
        "environment.name",
        "environment.base_url",
        "openapi",
        "scope",
        "scope.allow",
        "scope.authorization",
        "scope.authorization.reference",
        "scope.authorization.valid_until",
        "scope.windows",
        "limits",
        "limits.requests_per_second",
        "auth",
        "auth.token_path",
        "auth.accounts",
        "scope.allow.0.host",
        "scope.allow.0.paths",
        "scope.allow.0.methods",
        "cleanup.script",
        "cleanup.connection",
        "cleanup.requires_confirmation",
    ],
)
def test_from_data_lists_field_path_when_a_required_field_is_missing(path: str) -> None:
    error = error_for(removed(path))

    assert path.replace(".0.", "[0].") in error.message
    assert "ausente" in error.message or "type" in error.message
    assert error.hint


def test_from_data_explains_type_is_missing_when_auth_has_no_type() -> None:
    error = error_for(removed("auth.type"))

    assert "auth: campo 'type' ausente" in error.message


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("scrope", "scrope"),
        ("limits.requests_per_secod", "limits.requests_per_secod"),
        ("scope.alow", "scope.alow"),
        ("scope.allow.0.metohds", "scope.allow[0].metohds"),
        ("environment.url", "environment.url"),
        ("auth.accounts.0.pasword", "auth.accounts[0].pasword"),
        ("cleanup.confirm", "cleanup.confirm"),
    ],
)
def test_from_data_rejects_unknown_field_when_there_is_a_typo(path: str, expected: str) -> None:
    data = valid_data()
    cursor: object = data
    *parents, last = path.split(".")
    for part in parents:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cast(Data, cursor)[part]
    cast(Data, cursor)[last] = "x"

    error = error_for(data)

    assert f"{expected}: campo desconhecido" in error.message


def test_from_data_lists_every_problem_when_several_fields_are_invalid() -> None:
    data = valid_data()
    data["product"] = "Produto Inválido"
    data["limits"] = {
        "requests_per_second": 0,
        "max_duration_minutes": 9999,
        "zap_threads_per_host": 2,
    }
    data["extra_top"] = 1

    error = error_for(data)

    assert "product:" in error.message
    assert "limits.requests_per_second:" in error.message
    assert "limits.max_duration_minutes:" in error.message
    assert "extra_top:" in error.message
    assert "4 problema(s)" in error.message


# --------------------------------------------------------------------- valores


@pytest.mark.parametrize(
    ("path", "value"),
    [
        pytest.param("product", "Agenda", id="product_uppercase"),
        pytest.param("product", "", id="product_empty"),
        pytest.param("product", "a/b", id="product_with_slash"),
        pytest.param("product", "../x", id="product_traversal"),
        pytest.param("environment.name", "Homolog Env", id="env_name_invalid"),
        pytest.param("environment.base_url", "ftp://agenda.hml.exemplo.com.br", id="base_url_ftp"),
        pytest.param("environment.base_url", "agenda.hml.exemplo.com.br", id="base_url_no_scheme"),
        pytest.param(
            "environment.base_url", "https://agenda.hml.exemplo.com.br?x=1", id="base_url_query"
        ),
        pytest.param(
            "environment.base_url", "https://agenda.hml.exemplo.com.br#x", id="base_url_fragment"
        ),
        pytest.param(
            "environment.base_url", "https://u:p@agenda.hml.exemplo.com.br", id="base_url_userinfo"
        ),
        pytest.param("openapi", "/etc/passwd", id="openapi_absolute"),
        pytest.param("openapi", "../fora.json", id="openapi_parent"),
        pytest.param("openapi", "a/../../b.json", id="openapi_inner_parent"),
        pytest.param("openapi", "C:\\x.json", id="openapi_windows_drive"),
        pytest.param("openapi", "a\\b.json", id="openapi_backslash"),
        pytest.param("openapi", "~/x.json", id="openapi_home"),
        pytest.param("openapi", "", id="openapi_empty"),
        pytest.param("openapi", "a\x00b", id="openapi_nul"),
        pytest.param("openapi", 5, id="openapi_not_text"),
        pytest.param("limits.requests_per_second", 0, id="rps_zero"),
        pytest.param("limits.requests_per_second", 1000, id="rps_over_max"),
        pytest.param("limits.max_duration_minutes", "60", id="duration_string"),
        pytest.param("limits.zap_threads_per_host", 100, id="threads_over_max"),
        pytest.param("scope.authorization.valid_until", "31/01/2027", id="date_wrong_format"),
        pytest.param("scope.authorization.reference", "", id="authorization_empty"),
        pytest.param("scope.windows", [], id="no_windows"),
        pytest.param("scope.windows", ["segunda 20h"], id="window_bad_format"),
        pytest.param("scope.windows", [5], id="window_not_text"),
        pytest.param("scope.windows", "seg-sex 20:00-06:00 UTC", id="windows_not_a_list"),
        pytest.param("scope.allow", [], id="no_allow_rules"),
        pytest.param("scope.allow.0.host", "*.exemplo.com.br", id="allow_wildcard_host"),
        pytest.param("scope.allow.0.methods", ["FETCH"], id="allow_unknown_method"),
        pytest.param("scope.deny_paths", ["sem-barra"], id="deny_without_slash"),
        pytest.param("auth.type", "client_credentials", id="auth_type_unsupported"),
        pytest.param("auth.accounts", [], id="auth_no_accounts"),
        pytest.param("cleanup.type", "postgres_sql", id="cleanup_type_unsupported"),
        pytest.param("cleanup.script", "/opt/x.sql", id="cleanup_script_absolute"),
        pytest.param("cleanup.script", "../x.sql", id="cleanup_script_parent"),
    ],
)
def test_from_data_raises_config_error_when_value_is_invalid(path: str, value: object) -> None:
    error = error_for(mutated(path, value))

    assert error.code == "CONFIG_ERROR"
    assert error.message.startswith("Perfil inválido")
    assert error.hint


def test_from_data_raises_config_error_when_section_has_wrong_container_type() -> None:
    error = error_for(mutated("limits", [1, 2, 3]))

    assert "limits: esperado um objeto" in error.message


# ------------------------------------------------------------ ambiente x escopo


def test_from_data_raises_config_error_when_base_url_host_is_not_in_scope() -> None:
    error = error_for(mutated("environment.base_url", "https://outro.exemplo.com.br"))

    assert "base_url" in error.message
    assert "scope.allow" in error.message


def test_from_data_raises_config_error_when_base_url_port_is_not_in_scope() -> None:
    error = error_for(mutated("environment.base_url", "https://agenda.hml.exemplo.com.br:8443"))

    assert "scope.allow" in error.message


def test_from_data_raises_config_error_when_base_url_scheme_differs_from_rule() -> None:
    error = error_for(mutated("environment.base_url", "http://agenda.hml.exemplo.com.br"))

    assert "scope.allow" in error.message


def test_from_data_accepts_base_url_with_uppercase_host_and_trailing_dot() -> None:
    profile = load(mutated("environment.base_url", "https://AGENDA.hml.exemplo.com.br./"))

    assert profile.environment.base_url.startswith("https://AGENDA")


def test_from_data_raises_config_error_when_login_path_is_outside_scope() -> None:
    data = valid_data()
    data["scope"]["allow"][0]["paths"] = ["/api/**"]  # type: ignore[index]  # navegação em dict de teste

    error = error_for(data)

    assert "login" in error.message


def test_from_data_raises_config_error_when_login_method_post_is_not_allowed() -> None:
    data = valid_data()
    data["scope"]["allow"][0]["methods"] = ["GET"]  # type: ignore[index]  # navegação em dict de teste

    error = error_for(data)

    assert "login" in error.message


def test_from_data_raises_config_error_when_login_path_is_denied() -> None:
    error = error_for(mutated("scope.deny_paths", ["/auth/**"]))

    assert "login" in error.message
    assert "deny_paths" in error.message


# -------------------------------------------------------------------- laboratório


def lab_data() -> Data:
    data = valid_data()
    data["environment"] = {"name": "lab", "base_url": "http://vampi:5000"}
    data["scope"]["allow"] = [  # type: ignore[index]  # navegação em dict de teste
        {
            "host": "vampi",
            "scheme": "http",
            "port": 5000,
            "allow_local": True,
            "paths": ["/**"],
            "methods": ["GET", "POST"],
        }
    ]
    return data


def test_from_data_accepts_lab_profile_when_rule_opts_into_local() -> None:
    assert load(lab_data()).environment.base_url == "http://vampi:5000"


def test_from_data_rejects_lab_profile_when_allow_local_is_missing() -> None:
    data = lab_data()
    del data["scope"]["allow"][0]["allow_local"]  # type: ignore[index]  # dict de teste

    error = error_for(data)

    assert "allow_local" in error.message


# ---------------------------------------------------------------------- segredos


@pytest.mark.parametrize(
    "path",
    [
        "auth.accounts.0.username",
        "auth.accounts.0.password",
        "cleanup.connection",
    ],
)
@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(LITERAL, id="plain_string"),
        pytest.param({"secret_ref": LITERAL}, id="literal_inside_secret_ref"),
        pytest.param({"secret_ref": "env:" + LITERAL}, id="lowercase_env_name"),
        pytest.param({"value": LITERAL}, id="wrong_key"),
        pytest.param({"secret_ref": "env:OK", "value": LITERAL}, id="literal_next_to_reference"),
        pytest.param([LITERAL], id="list_with_literal"),
    ],
)
def test_from_data_rejects_literal_secret_and_never_echoes_it_when_placed_in_secret_field(
    path: str, bad: object
) -> None:
    error = error_for(mutated(path, bad))

    assert LITERAL not in error.message
    assert LITERAL not in (error.hint or "")
    assert LITERAL not in str(error)
    assert LITERAL not in repr(error)
    assert path.replace(".0.", "[0].") in error.message


def test_from_data_rejects_api_key_literal_and_never_echoes_it() -> None:
    data = valid_data()
    data["auth"] = {
        "type": "api_key",
        "header_name": "X-API-Key",
        "accounts": [{"alias": "svc", "role": "servico", "api_key": LITERAL}],
    }

    error = error_for(data)

    assert LITERAL not in error.message
    assert "auth.accounts[0].api_key" in error.message


def test_from_data_does_not_echo_unknown_auth_type_value() -> None:
    error = error_for(mutated("auth.type", LITERAL))

    assert LITERAL not in error.message


def test_validation_error_hides_input_when_model_is_built_directly() -> None:
    with pytest.raises(ValidationError) as caught:
        PasswordLoginAuth.model_validate(
            {
                "type": "login_password",
                "token_path": "/auth/token",
                "accounts": [
                    {
                        "alias": "user_a",
                        "role": "r",
                        "username": {"secret_ref": "env:U"},
                        "password": LITERAL,
                    }
                ],
            }
        )

    assert LITERAL not in str(caught.value)


# ------------------------------------------------------------------- limpeza


@pytest.mark.parametrize("value", [False, None, "true", 1, 0, "yes"])
def test_from_data_rejects_cleanup_when_confirmation_is_not_literally_true(value: object) -> None:
    error = error_for(mutated("cleanup.requires_confirmation", value))

    assert "cleanup.requires_confirmation" in error.message


def test_from_data_explains_confirmation_is_mandatory_when_false() -> None:
    error = error_for(mutated("cleanup.requires_confirmation", False))

    assert "obrigatória" in error.message


# -------------------------------------------------------- autorização e janela


def test_ensure_runnable_passes_when_authorization_is_valid_and_window_is_open() -> None:
    profile = load(valid_data())

    profile.ensure_runnable(datetime(2026, 11, 10, 1, 0, tzinfo=UTC))  # seg 22:00 em São Paulo


def test_ensure_runnable_raises_scope_violation_when_authorization_expired() -> None:
    profile = load(valid_data())

    with pytest.raises(ScopeViolation, match="expirou"):
        profile.ensure_runnable(datetime(2027, 2, 2, 1, 0, tzinfo=UTC))


def test_ensure_runnable_raises_scope_violation_when_window_is_closed() -> None:
    profile = load(valid_data())

    with pytest.raises(ScopeViolation, match="janela"):
        profile.ensure_runnable(datetime(2026, 11, 10, 15, 0, tzinfo=UTC))  # terça 12:00


def test_ensure_runnable_raises_config_error_when_now_is_naive() -> None:
    profile = load(valid_data())

    with pytest.raises(ConfigError):
        profile.ensure_runnable(datetime(2026, 11, 10, 1, 0))


def test_ensure_runnable_opens_when_any_of_several_windows_is_open() -> None:
    data = mutated(
        "scope.windows",
        ["seg 08:00-09:00 America/Sao_Paulo", "sab 10:00-12:00 America/Sao_Paulo"],
    )

    load(data).ensure_runnable(datetime(2026, 11, 14, 14, 0, tzinfo=UTC))  # sáb 11:00 em SP
