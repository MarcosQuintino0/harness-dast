"""Expressões do contexto do ZAP derivadas do escopo do perfil."""

import re

import pytest

from harness_dast.domain.scope import Scope, ScopeRule
from harness_dast.domain.zap_scope import (
    REPLACER_RULE_PREFIX,
    context_exclude_regexes,
    context_include_regexes,
    path_regex,
)

HOST = "api.permitido.com"


def scope(**rule: object) -> Scope:
    data = {"host": HOST, "paths": ["/api/**"], "methods": ["GET"]} | rule
    return Scope(
        allow=(ScopeRule.model_validate(data),), deny_paths=("/api/admin/**", "/api/conta")
    )


def matches(patterns: tuple[str, ...], url: str) -> bool:
    return any(re.fullmatch(p, url) for p in patterns)


def test_included_urls_follow_the_allow_rule() -> None:
    include = context_include_regexes(scope())

    assert matches(include, f"https://{HOST}/api/x")
    assert matches(include, f"https://{HOST}:443/api/x/y?z=1")
    assert matches(include, f"https://{HOST}/api")
    assert not matches(include, f"https://{HOST}/outro")
    assert not matches(include, "https://outro.example.org/api/x")
    assert not matches(include, f"http://{HOST}/api/x")
    assert not matches(include, f"https://{HOST}.evil.example.org/api/x")
    assert not matches(include, f"https://{HOST}:8443/api/x")


def test_a_non_default_port_is_required_when_the_rule_declares_it() -> None:
    include = context_include_regexes(scope(port=8443))

    assert matches(include, f"https://{HOST}:8443/api/x")
    assert not matches(include, f"https://{HOST}/api/x")


def test_single_star_matches_exactly_one_segment() -> None:
    regex = path_regex("/a/*/c")

    assert re.fullmatch(regex, "/a/b/c")
    assert not re.fullmatch(regex, "/a/c")
    assert not re.fullmatch(regex, "/a/b/x/c")


def test_root_pattern_matches_only_the_root() -> None:
    assert re.fullmatch(path_regex("/"), "/")
    assert not re.fullmatch(path_regex("/"), "/x")


def test_excluded_urls_are_the_deny_paths_on_any_host() -> None:
    exclude = context_exclude_regexes(scope())

    assert matches(exclude, f"https://{HOST}/api/admin/x")
    assert matches(exclude, "http://qualquer.example.org:81/api/conta")
    assert not matches(exclude, f"https://{HOST}/api/x")


def test_dots_in_hosts_are_escaped() -> None:
    include = context_include_regexes(scope())

    assert not matches(include, "https://apiXpermitidoXcom/api/x")


def test_replacer_rules_of_the_harness_share_one_prefix() -> None:
    assert REPLACER_RULE_PREFIX == "hdast-"


@pytest.mark.parametrize("count", [1, 2])
def test_one_regex_per_rule_and_pattern_without_duplicates(count: int) -> None:
    rule = ScopeRule(host=HOST, paths=tuple(f"/p{i}/**" for i in range(count)), methods=("GET",))

    assert len(context_include_regexes(Scope(allow=(rule, rule)))) == count
