"""Impressão digital dos blocos de proteção: o que muda o resumo e o que não muda (ADR 0037)."""

import copy
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from harness_dast.domain.auth import ApiKeyAuth, PasswordLoginAuth
from harness_dast.domain.authz_config import AuthzConfig
from harness_dast.domain.profile import CleanupConfig, ProductProfile
from harness_dast.domain.scan_config import ScanConfig
from harness_dast.domain.scope_fingerprint import (
    BLOCK_IDS,
    FINGERPRINT_VERSION,
    block_digests,
    combine_digests,
    describe_block,
    protected_blocks,
)
from tests.fakes.profile_data import dump_yaml, valid_profile_data

Mutation = Callable[[dict[str, Any]], None]

SECOND_RULE = {"host": "api2.hml.acme-teste.net.br", "paths": ["/v2/**"], "methods": ["GET"]}
SECOND_ACCOUNT = {
    "alias": "user_b",
    "role": "usuario",
    "username": {"secret_ref": "env:ACME_USER_B_LOGIN"},
    "password": {"secret_ref": "env:ACME_USER_B_SENHA"},
}


def digests(data: dict[str, Any]) -> dict[str, str]:
    return block_digests(ProductProfile.from_data(data))


def overall(data: dict[str, Any]) -> str:
    profile = ProductProfile.from_data(data)
    return combine_digests(profile.product, block_digests(profile))


def mutated(mutation: Mutation) -> dict[str, Any]:
    data = copy.deepcopy(valid_profile_data())
    mutation(data)
    return data


def _swap_first_account_secret(data: dict[str, Any]) -> None:
    data["auth"]["accounts"][0]["password"] = {"secret_ref": "env:ACME_OUTRO_SEGREDO"}


def _cleanup(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "type": "oracle_sql",
        "script": "./cleanup/cleanup.sql",
        "connection": {"secret_ref": "env:ACME_ORACLE_LIMPEZA"},
        "requires_confirmation": True,
        "user": {"secret_ref": "env:ACME_ORACLE_USER"},
        "password": {"secret_ref": "env:ACME_ORACLE_SENHA"},
        "allowed_tables": ["PEDIDOS"],
        "max_rows": 100,
    }
    return {**base, **overrides}


# (mutação, bloco que precisa mudar)
PROTECTED_CHANGES: list[tuple[str, Mutation, str]] = [
    ("environment.name", lambda d: d["environment"].update(name="outro"), "environment"),
    (
        "environment.base_url",
        lambda d: d["environment"].update(base_url="https://api.hml.acme-teste.net.br/api"),
        "environment",
    ),
    ("allow.regra nova", lambda d: d["scope"]["allow"].append(SECOND_RULE), "scope.allow"),
    (
        "allow.caminho novo",
        lambda d: d["scope"]["allow"][0]["paths"].append("/extra/**"),
        "scope.allow",
    ),
    (
        "allow.método novo",
        lambda d: d["scope"]["allow"][0].update(methods=["GET", "POST", "PUT"]),
        "scope.allow",
    ),
    (
        "allow.esquema",
        lambda d: d["scope"]["allow"].append(
            {**SECOND_RULE, "host": "api.hml.acme-teste.net.br", "scheme": "http"}
        ),
        "scope.allow",
    ),
    (
        "allow.porta",
        lambda d: d["scope"]["allow"].append(
            {**SECOND_RULE, "host": "api.hml.acme-teste.net.br", "port": 8443}
        ),
        "scope.allow",
    ),
    ("deny.removido", lambda d: d["scope"].update(deny_paths=[]), "scope.deny_paths"),
    (
        "deny.acrescentado",
        lambda d: d["scope"]["deny_paths"].append("/api/interno/**"),
        "scope.deny_paths",
    ),
    ("path_mode wide", lambda d: d["scope"].update(path_mode="wide"), "scope.path_mode"),
    (
        "authorization.reference",
        lambda d: d["scope"]["authorization"].update(reference="CHG-9999"),
        "scope.authorization",
    ),
    (
        "authorization.valid_until",
        lambda d: d["scope"]["authorization"].update(valid_until="2999-12-30"),
        "scope.authorization",
    ),
    (
        "janela",
        lambda d: d["scope"].update(windows=["seg-sex 20:00-06:00 America/Sao_Paulo"]),
        "scope.windows",
    ),
    (
        "janela extra",
        lambda d: d["scope"]["windows"].append("sab 10:00-12:00 UTC"),
        "scope.windows",
    ),
    ("limits.rps", lambda d: d["limits"].update(requests_per_second=6), "limits"),
    ("limits.duração", lambda d: d["limits"].update(max_duration_minutes=61), "limits"),
    ("limits.threads", lambda d: d["limits"].update(zap_threads_per_host=3), "limits"),
    (
        "auth.token_path",
        lambda d: d["auth"].update(token_path="/api/auth/login2"),  # noqa: S106 - caminho
        "auth",
    ),
    ("auth.conta nova", lambda d: d["auth"]["accounts"].append(SECOND_ACCOUNT), "auth"),
    ("auth.papel", lambda d: d["auth"]["accounts"][0].update(role="admin"), "auth"),
    ("auth.apelido", lambda d: d["auth"]["accounts"][0].update(alias="user_z"), "auth"),
    ("auth.secret_ref", _swap_first_account_secret, "auth"),
    ("auth.login_limit", lambda d: d["auth"].update(login_limit={"max_per_minute": 30}), "auth"),
    ("scan.strength", lambda d: d.update(scan={"strength": "HIGH"}), "scan"),
    ("scan.mutating_methods", lambda d: d.update(scan={"mutating_methods": ["PUT"]}), "scan"),
    (
        "scan.url_path_injection",
        lambda d: d.update(scan={"url_path_injection": False}),
        "scan",
    ),
    (
        "authz.vertical_methods",
        lambda d: d.update(authz={"vertical_methods": ["GET", "POST"]}),
        "authz",
    ),
    ("scan.threshold", lambda d: d.update(scan={"threshold": "HIGH"}), "scan"),
    ("scan.fail_on", lambda d: d.update(scan={"fail_on": "high"}), "scan"),
    ("scan.disable_rules", lambda d: d.update(scan={"disable_rules": [40018]}), "scan"),
    ("scan.max_scan_minutes", lambda d: d.update(scan={"max_scan_minutes": 30}), "scan"),
    ("scan.max_rule_minutes", lambda d: d.update(scan={"max_rule_minutes": 5}), "scan"),
    (
        "scan.token_refresh_seconds",
        lambda d: d.update(scan={"token_refresh_seconds": 600}),
        "scan",
    ),
    (
        "authz.public_operations",
        lambda d: d.update(authz={"public_operations": ["ler"]}),
        "authz",
    ),
    (
        "authz.disabled_checks",
        lambda d: d.update(authz={"disabled_checks": ["vertical"]}),
        "authz",
    ),
    (
        "authz.disabled_checks (verificações de acesso, ADR 0039)",
        lambda d: d.update(authz={"disabled_checks": ["anonymous_access", "tampered_token"]}),
        "authz",
    ),
    (
        "authz.mass_assignment_fields",
        lambda d: d.update(authz={"mass_assignment_fields": [{"name": "tipo", "value": "x"}]}),
        "authz",
    ),
    ("authz.role_order", lambda d: d.update(authz={"role_order": ["usuario", "admin"]}), "authz"),
    (
        "authz.volatile_fields",
        lambda d: d.update(authz={"volatile_fields": ["criadoEm"]}),
        "authz",
    ),
    ("authz.allow_writes", lambda d: d.update(authz={"allow_writes": True}), "authz"),
    ("cleanup.novo", lambda d: d.update(cleanup=_cleanup()), "cleanup"),
    ("cleanup.script", lambda d: d.update(cleanup=_cleanup(script="./outro.sql")), "cleanup"),
    (
        "cleanup.connection",
        lambda d: d.update(cleanup=_cleanup(connection={"secret_ref": "env:OUTRO_BANCO"})),
        "cleanup",
    ),
    (
        "cleanup.user",
        lambda d: d.update(cleanup=_cleanup(user={"secret_ref": "env:U2"})),
        "cleanup",
    ),
    (
        "cleanup.password",
        lambda d: d.update(cleanup=_cleanup(password={"secret_ref": "env:P2"})),
        "cleanup",
    ),
    (
        "cleanup.allowed_tables",
        lambda d: d.update(cleanup=_cleanup(allowed_tables=["CLIENTES"])),
        "cleanup",
    ),
    ("cleanup.max_rows", lambda d: d.update(cleanup=_cleanup(max_rows=999)), "cleanup"),
    ("cleanup.db_schema", lambda d: d.update(cleanup=_cleanup(db_schema="OUTRO")), "cleanup"),
]

# Ajustes que o agente faz depois da aprovação: nada disto pode invalidá-la.
UNPROTECTED_CHANGES: list[tuple[str, Mutation]] = [
    ("openapi", lambda d: d.update(openapi="./outro.json")),
    ("auth.csrf", lambda d: d["auth"].update(csrf={"fetch_path": "/api/csrf"})),
    ("auth.request_encoding", lambda d: d["auth"].update(request_encoding="form")),
    ("auth.username_field", lambda d: d["auth"].update(username_field="email")),
    ("auth.token_scheme", lambda d: d["auth"].update(token_scheme="Token")),  # noqa: S106
    (
        "auth.token_expired",
        lambda d: d["auth"].update(token_expired={"field": "code", "value": "EXPIRADO"}),
    ),
    ("probe.health_path", lambda d: d.update(probe={"health_path": "/api/saude"})),
    ("probe.setup_path", lambda d: d.update(probe={"setup_path": "/api/saude"})),
]


def test_digests_are_stable_across_calls() -> None:
    data = valid_profile_data()

    assert digests(data) == digests(copy.deepcopy(data))
    assert overall(data) == overall(copy.deepcopy(data))


def test_every_protected_block_has_a_digest_in_display_order() -> None:
    profile = ProductProfile.from_data(valid_profile_data())

    assert tuple(block_digests(profile)) == BLOCK_IDS
    assert tuple(protected_blocks(profile)) == BLOCK_IDS


def test_yaml_key_order_comments_and_spacing_do_not_change_the_digests() -> None:
    data = valid_profile_data()
    reordered = {key: data[key] for key in reversed(list(data))}
    text = "# comentário que não conta\n\n" + dump_yaml(reordered).replace("\n", "\n\n")
    loaded = yaml.safe_load(text)

    assert digests(loaded) == digests(data)
    assert overall(loaded) == overall(data)


def test_order_of_rules_paths_methods_deny_and_windows_does_not_change_the_digests() -> None:
    first = mutated(lambda d: d["scope"]["allow"].append(SECOND_RULE))
    first["scope"]["deny_paths"] = ["/a/**", "/b/**"]
    first["scope"]["windows"] = ["sab 10:00-12:00 UTC", "seg-dom 00:00-24:00 UTC"]
    second = copy.deepcopy(first)
    second["scope"]["allow"].reverse()
    second["scope"]["allow"][1]["paths"] = list(reversed(second["scope"]["allow"][1]["paths"]))
    second["scope"]["deny_paths"].reverse()
    second["scope"]["windows"].reverse()

    assert overall(first) == overall(second)


def test_order_of_accounts_matters_because_the_first_one_is_the_default() -> None:
    first = mutated(lambda d: d["auth"]["accounts"].append(SECOND_ACCOUNT))
    second = copy.deepcopy(first)
    second["auth"]["accounts"].reverse()

    assert digests(first)["auth"] != digests(second)["auth"]


@pytest.mark.parametrize(
    ("mutation", "block"),
    [pytest.param(m, b, id=name) for name, m, b in PROTECTED_CHANGES],
)
def test_changing_a_protected_field_changes_exactly_its_block(
    mutation: Mutation, block: str
) -> None:
    before = digests(valid_profile_data())
    after_data = mutated(mutation)

    after = digests(after_data)

    assert [name for name in BLOCK_IDS if before[name] != after[name]] == [block]
    assert overall(valid_profile_data()) != overall(after_data)


@pytest.mark.parametrize("mutation", [pytest.param(m, id=name) for name, m in UNPROTECTED_CHANGES])
def test_changing_a_field_outside_the_protection_keeps_every_digest(mutation: Mutation) -> None:
    base = valid_profile_data()
    changed = mutated(mutation)

    assert digests(changed) == digests(base)
    assert overall(changed) == overall(base)


def test_account_map_and_default_account_do_not_change_the_digests() -> None:
    base = mutated(lambda d: d["auth"]["accounts"].append(SECOND_ACCOUNT))
    routed = copy.deepcopy(base)
    routed["auth"]["default_account"] = "user_b"
    routed["auth"]["account_map"] = [{"account": "user_b", "path": "/api/admin/**"}]

    assert digests(routed) == digests(base)


def test_explicit_default_values_hash_like_omitted_ones() -> None:
    explicit = mutated(
        lambda d: d.update(
            scan={"strength": "LOW", "url_path_injection": True, "mutating_methods": []},
            authz={"vertical_methods": ["GET", "HEAD"]},
        )
    )
    explicit["scope"]["path_mode"] = "strict"

    assert overall(explicit) == overall(valid_profile_data())


def test_overall_digest_depends_on_the_product_name() -> None:
    one = ProductProfile.from_data(valid_profile_data("um"))
    other = ProductProfile.from_data(valid_profile_data("outro"))

    assert block_digests(one) == block_digests(other)
    assert combine_digests("um", block_digests(one)) != combine_digests(
        "outro", block_digests(other)
    )


def test_describe_block_names_known_blocks_and_falls_back_to_the_identifier() -> None:
    assert "limites" in describe_block("limits")
    assert describe_block("bloco.novo") == "bloco.novo"


def test_cleanup_changes_are_detected_against_an_existing_cleanup_block() -> None:
    base = mutated(lambda d: d.update(cleanup=_cleanup()))
    changed = mutated(lambda d: d.update(cleanup=_cleanup(max_rows=5000)))

    before, after = digests(base), digests(changed)

    assert [name for name in BLOCK_IDS if before[name] != after[name]] == ["cleanup"]


def test_reordering_set_like_scan_and_authz_fields_does_not_change_the_digests() -> None:
    first = mutated(
        lambda d: d.update(
            scan={"disable_rules": [40018, 40012], "mutating_methods": ["PUT", "PATCH"]},
            authz={
                "public_operations": ["a", "b"],
                "disabled_checks": ["vertical", "horizontal"],
                "volatile_fields": ["x", "y"],
            },
        )
    )
    second = copy.deepcopy(first)
    second["scan"] = {"disable_rules": [40012, 40018], "mutating_methods": ["PATCH", "PUT"]}
    second["authz"] = {
        "public_operations": ["b", "a"],
        "disabled_checks": ["horizontal", "vertical"],
        "volatile_fields": ["y", "x"],
    }

    assert overall(first) == overall(second)


def test_role_order_is_a_sequence_and_its_order_matters() -> None:
    first = mutated(lambda d: d.update(authz={"role_order": ["usuario", "admin"]}))
    second = mutated(lambda d: d.update(authz={"role_order": ["admin", "usuario"]}))

    assert digests(first)["authz"] != digests(second)["authz"]


def test_the_fingerprint_version_is_two_so_version_one_approvals_are_refused() -> None:
    assert FINGERPRINT_VERSION == 2


# Campos de `auth` que entram no bloco `auth`; os demais campos de `auth` ficam livres
# (ADR 0037): só o agente os ajusta para alcançar operações e nenhum muda alcance, conta, carga,
# duração nem o que é relatado.
AUTH_PROTECTED: frozenset[str] = frozenset(
    {"type", "token_path", "header_name", "accounts", "login_limit"}
)
AUTH_FREE: frozenset[str] = frozenset(
    {
        "csrf",
        "account_map",
        "default_account",
        "token_expired",
        "request_encoding",
        "username_field",
        "password_field",
        "token_response_field",
        "token_header",
        "token_scheme",
    }
)
# Blocos que entram inteiros (os campos de cada um estão no `model_dump` do bloco).
TOP_LEVEL_PROTECTED: frozenset[str] = frozenset(
    {"product", "environment", "scope", "limits", "auth", "scan", "authz", "cleanup"}
)
TOP_LEVEL_FREE: frozenset[str] = frozenset({"schema_version", "openapi", "probe"})


def test_every_top_level_profile_field_is_classified_as_protected_or_free() -> None:
    fields = set(ProductProfile.model_fields)

    assert fields == TOP_LEVEL_PROTECTED | TOP_LEVEL_FREE


def test_every_auth_field_is_in_the_auth_block_or_in_the_free_list() -> None:
    auth_fields = set(PasswordLoginAuth.model_fields) | set(ApiKeyAuth.model_fields)

    assert auth_fields == AUTH_PROTECTED | AUTH_FREE


def test_every_scan_authz_and_cleanup_field_is_covered_by_the_dump_of_its_block() -> None:
    # Chave nova do `authz` no padrão fica de fora do cálculo; fora do padrão, ela entra.
    changed = {
        "allow_writes": True,
        "derive_mass_candidates": False,
        "max_derived_candidates": 3,
        "mass_assignment_methods": ["PUT"],
        "id_parameters": ["cpf"],
        "access_matrix": [{"operation": "x", "allow": ["a"], "deny": ["b"]}],
    }
    profile = ProductProfile.from_data(
        mutated(
            lambda d: d.update(
                cleanup=_cleanup(), authz=changed, scan={"include_outcomes": ["not_found"]}
            )
        )
    )
    blocks = protected_blocks(profile)

    for name, model in (("scan", ScanConfig), ("authz", AuthzConfig), ("cleanup", CleanupConfig)):
        block = blocks[name]
        assert isinstance(block, dict)
        assert set(block) == set(model.model_fields), name


@pytest.mark.parametrize(
    "authz",
    [
        {},
        {"derive_mass_candidates": True},
        {"max_derived_candidates": 6},
        {"mass_assignment_methods": ["PUT", "POST", "PATCH"]},
        {"id_parameters": []},
    ],
)
def test_default_mass_keys_hash_like_a_profile_from_before_adr_0040(authz: dict[str, Any]) -> None:
    explicit = mutated(lambda d: d.update(authz=authz))

    assert digests(explicit) == digests(valid_profile_data())
    assert overall(explicit) == overall(valid_profile_data())


@pytest.mark.parametrize(
    "authz",
    [
        {"derive_mass_candidates": False},
        {"max_derived_candidates": 7},
        {"mass_assignment_methods": ["PUT", "PATCH"]},
        {"id_parameters": ["cpf"]},
        {"id_parameters": ["cpf", "matricula"]},
    ],
)
def test_changing_a_mass_key_changes_only_the_authz_digest(authz: dict[str, Any]) -> None:
    before = digests(valid_profile_data())
    after = digests(mutated(lambda d: d.update(authz=authz)))

    assert {name for name in before if before[name] != after[name]} == {"authz"}


def test_allow_writes_false_hashes_like_a_profile_that_never_had_the_key() -> None:
    explicit = mutated(lambda d: d.update(authz={"allow_writes": False}))

    assert digests(explicit) == digests(valid_profile_data())
    assert overall(explicit) == overall(valid_profile_data())


def test_allow_writes_true_changes_only_the_authz_digest() -> None:
    before = digests(valid_profile_data())
    after = digests(mutated(lambda d: d.update(authz={"allow_writes": True})))

    assert [name for name in before if before[name] != after[name]] == ["authz"]


TABLE = [
    {"operation": "criarMedico", "allow": ["admin"], "deny": ["paciente", "recepcao"]},
    {"operation": "getConsulta", "allow": ["paciente", "medico"], "deny": ["recepcao"]},
]


def test_an_empty_or_absent_access_matrix_hashes_like_a_profile_from_before_adr_0041() -> None:
    explicit = mutated(lambda d: d.update(authz={"access_matrix": []}))

    assert digests(explicit) == digests(valid_profile_data())
    assert overall(explicit) == overall(valid_profile_data())
    block = protected_blocks(ProductProfile.from_data(explicit))["authz"]
    assert isinstance(block, dict)
    assert "access_matrix" not in block


def test_filling_the_access_matrix_changes_only_the_authz_digest() -> None:
    before = digests(valid_profile_data())
    after = digests(mutated(lambda d: d.update(authz={"access_matrix": TABLE})))

    assert [name for name in before if before[name] != after[name]] == ["authz"]


def test_reordering_the_rules_and_the_roles_does_not_change_the_digests() -> None:
    shuffled = [
        {"operation": "getConsulta", "allow": ["medico", "paciente"], "deny": ["recepcao"]},
        {"operation": "criarMedico", "allow": ["admin"], "deny": ["recepcao", "paciente"]},
    ]

    one = digests(mutated(lambda d: d.update(authz={"access_matrix": TABLE})))
    two = digests(mutated(lambda d: d.update(authz={"access_matrix": shuffled})))

    assert one == two


@pytest.mark.parametrize(
    "change",
    [
        lambda rules: rules[1].update(deny=[]),
        lambda rules: rules[0].update(deny=["paciente"]),
        lambda rules: rules[0].update(allow=["admin", "medico"]),
        lambda rules: rules[0].update(operation="criarMedicos"),
        lambda rules: rules.pop(),
    ],
)
def test_taking_a_role_out_of_deny_or_editing_a_rule_changes_only_the_authz_digest(
    change: Callable[[list[dict[str, Any]]], object],
) -> None:
    edited = copy.deepcopy(TABLE)
    change(edited)

    before = digests(mutated(lambda d: d.update(authz={"access_matrix": TABLE})))
    after = digests(mutated(lambda d: d.update(authz={"access_matrix": edited})))

    assert [name for name in before if before[name] != after[name]] == ["authz"]


def _with_outcomes(*classes: str) -> dict[str, Any]:
    return mutated(lambda d: d.setdefault("scan", {}).update(include_outcomes=list(classes)))


@pytest.mark.parametrize("scan", [None, {}, {"include_outcomes": []}])
def test_an_empty_include_outcomes_hashes_like_a_profile_from_before_adr_0050(
    scan: dict[str, Any] | None,
) -> None:
    data = copy.deepcopy(valid_profile_data())
    if scan is not None:
        data["scan"] = scan
    profile = ProductProfile.from_data(data)

    assert "include_outcomes" not in protected_blocks(profile)["scan"]  # type: ignore[operator]  # o bloco é um mapa
    assert digests(data) == digests(copy.deepcopy(valid_profile_data()))
    assert overall(data) == overall(copy.deepcopy(valid_profile_data()))


def test_the_scan_digest_of_a_legacy_profile_is_the_recorded_one() -> None:
    legacy_scan = {
        "strength": "LOW",
        "threshold": "MEDIUM",
        "url_path_injection": True,
        "mutating_methods": [],
        "disable_rules": [],
        "max_scan_minutes": 10,
        "max_rule_minutes": 2,
        "token_refresh_seconds": 120,
        "fail_on": "none",
    }
    profile = ProductProfile.from_data(valid_profile_data())

    assert protected_blocks(profile)["scan"] == legacy_scan
    # Valor calculado com o código anterior ao ADR 0050: aprovação antiga continua valendo.
    assert (
        digests(valid_profile_data())["scan"]
        == "6abc9ab9206f45fd439e72920d5e6e59368908e2725f866df15aba6e1b1fe202"
    )


def test_turning_include_outcomes_on_changes_only_the_scan_block() -> None:
    before = digests(valid_profile_data())

    after = digests(_with_outcomes("not_found"))

    assert {name for name in before if before[name] != after[name]} == {"scan"}


def test_include_outcomes_order_does_not_change_the_fingerprint() -> None:
    assert digests(_with_outcomes("not_found", "conflict")) == digests(
        _with_outcomes("conflict", "not_found")
    )


def test_different_classes_give_different_fingerprints() -> None:
    assert (
        digests(_with_outcomes("not_found"))["scan"] != digests(_with_outcomes("conflict"))["scan"]
    )
