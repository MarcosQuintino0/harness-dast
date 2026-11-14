"""Impressão digital dos blocos de proteção: o que muda o resumo e o que não muda (ADR 0037)."""

import copy
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_fingerprint import (
    BLOCK_IDS,
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
    ("scan.threshold", lambda d: d.update(scan={"threshold": "HIGH"})),
    ("scan.fail_on", lambda d: d.update(scan={"fail_on": "high"})),
    ("scan.disable_rules", lambda d: d.update(scan={"disable_rules": [40018]})),
    ("authz.public_operations", lambda d: d.update(authz={"public_operations": ["ler"]})),
    ("authz.disabled_checks", lambda d: d.update(authz={"disabled_checks": ["vertical"]})),
    (
        "cleanup",
        lambda d: d.update(
            cleanup={
                "type": "oracle_sql",
                "script": "./cleanup/cleanup.sql",
                "connection": {"secret_ref": "env:ACME_ORACLE_LIMPEZA"},
                "requires_confirmation": True,
            }
        ),
    ),
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
