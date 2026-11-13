"""Escopo do contexto do ZAP (camada 2 do ADR 0008) derivado do `Scope` do perfil.

O contexto do ZAP é restrito aos hosts e caminhos autorizados. Ele NÃO substitui o
`ScopeGuard` (o spike do M0 mostrou que o varredor gera caminhos fora da expressão do
contexto), mas fecha a varredura sem `contextId` e recusa URL inicial fora dele. Este módulo é
puro.
"""

import re
from typing import Final

from harness_dast.domain.pathpattern import parse_pattern
from harness_dast.domain.scope import Scope, ScopeRule
from harness_dast.domain.urlnorm import default_port

REPLACER_RULE_PREFIX: Final = "hdast-"
"""Prefixo obrigatório do nome (descrição) de toda regra do Replacer criada pelo harness; a
limpeza de regras antigas remove apenas o que começa com ele."""

TESTED_ZAP_PREFIX: Final = "2.17."
"""Versões do ZAP validadas no spike do M0; outra versão é avisada, não bloqueada."""


def _segment_regex(segment: str) -> str:
    if segment == "*":
        return "/[^/]+"
    if segment == "**":
        return "(?:/.*)?"
    return "/" + re.escape(segment)


def path_regex(pattern: str) -> str:
    """Converte um padrão de caminho do escopo em expressão regular (compatível com Java)."""
    segments = parse_pattern(pattern)
    if not segments:
        return "/?"
    return "".join(_segment_regex(segment) for segment in segments) + "/?"


def _origin_regex(rule: ScopeRule) -> str:
    standard = default_port(rule.scheme)
    port = rule.port or standard
    # O ZAP omite a porta padrão nas URLs que registra.
    suffix = f"(?::{port})?" if port == standard else f":{port}"
    return f"{re.escape(rule.scheme)}://{re.escape(rule.host)}{suffix}"


def context_include_regexes(scope: Scope) -> tuple[str, ...]:
    """Expressões de inclusão do contexto: uma por (regra, padrão de caminho)."""
    found = (
        f"^{_origin_regex(rule)}{path_regex(pattern)}(?:\\?.*)?$"
        for rule in scope.allow
        for pattern in rule.paths
    )
    return tuple(dict.fromkeys(found))


def context_exclude_regexes(scope: Scope) -> tuple[str, ...]:
    """Expressões de exclusão do contexto: `deny_paths` em qualquer host."""
    return tuple(
        f"^https?://[^/]+(?::\\d+)?{path_regex(pattern)}(?:\\?.*)?$" for pattern in scope.deny_paths
    )
