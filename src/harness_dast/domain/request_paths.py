"""Caminhos do OpenAPI no modo pedido mínimo: escopo padrão e sugestão de negados (ADR 0120).

`{x}` num modelo de caminho vira o curinga `*` da cerca, que casa exatamente um segmento (um
segmento com `{` e outro texto, como `{id}.json`, também vira `*`: casa um pouco a mais, nunca
um segmento a mais). A sugestão de `scope.deny_paths` é heurística, por nome de segmento
literal: recuperação, esquecimento e troca de senha, logout, exclusão de conta e administração.
Os trechos de nome são buscados por substring. `otp` exige uma palavra inteira, separada por
`-`, `_`, `.`, espaço ou fronteira camelCase, porque `check-otp` conclui a recuperação de senha
no crAPI.
Um caminho perigoso com nome inesperado escapa dela; por isso o agente pode acrescentar
caminhos a partir da documentação de negócio e a pessoa revisa tudo na aprovação. Este módulo
é puro e só soma: nada aqui remove um caminho negado.
"""

import re
from collections.abc import Iterable
from typing import Final

from harness_dast.domain.pathpattern import format_pattern, parse_pattern

_NAME_KEYWORDS: Final = (
    "forgot",
    "forget",
    "reset",
    "recover",
    "password",
    "passwd",
    "logout",
    "signout",
    "admin",
    "deleteaccount",
    "removeaccount",
    "closeaccount",
    "deactivate",
    "deleteuser",
    "deleteme",
    "unregister",
)
"""Trechos de nome (minúsculas, sem `-` nem `_`) que fazem o caminho entrar na sugestão."""
_SEPARATORS: Final = str.maketrans("", "", "-_. ")
_WORD_BOUNDARIES: Final = re.compile(r"[-_. ]+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def to_scope_pattern(template: str, prefix: str = "") -> str | None:
    """Converte um modelo de caminho do OpenAPI num padrão de `scope`, ou `None` se não cabe.

    Args:
        template: Caminho do OpenAPI, como `/users/{id}/password`.
        prefix: Caminho do endereço base (`/api`), somado antes do modelo.

    Returns:
        O padrão canônico (`/api/users/*/password`) ou `None` quando a cerca não aceita o
        padrão (caractere proibido, `*` literal): o caminho fica de fora do escopo.
    """
    segments = [part for part in (prefix + template).split("/") if part != ""]
    if any("*" in part for part in segments):
        return None  # `*` literal no OpenAPI não pode virar curinga da cerca
    wildcard = ["*" if "{" in part or "}" in part else part for part in segments]
    try:
        return format_pattern(parse_pattern("/" + "/".join(wildcard)))
    except ValueError:
        return None


def _is_dangerous(template: str) -> bool:
    for segment in template.split("/"):
        if "{" in segment or "}" in segment:
            continue
        name = segment.lower().translate(_SEPARATORS)
        if any(keyword in name for keyword in _NAME_KEYWORDS):
            return True
        if any(word.lower() == "otp" for word in _WORD_BOUNDARIES.split(segment)):
            return True
    return False


def allow_patterns(templates: Iterable[str], prefix: str) -> tuple[tuple[str, ...], int]:
    """Padrões de `scope.allow` de todos os caminhos do OpenAPI, sem repetição.

    Returns:
        Os padrões, na ordem do documento, e quantos caminhos ficaram de fora porque a cerca
        não aceita o padrão.
    """
    patterns: dict[str, None] = {}
    skipped = 0
    for template in templates:
        pattern = to_scope_pattern(template, prefix)
        if pattern is None:
            skipped += 1
        else:
            patterns[pattern] = None
    return tuple(patterns), skipped


def suggest_deny_paths(
    templates: Iterable[str], prefix: str, keep: frozenset[str]
) -> tuple[str, ...]:
    """Sugere `scope.deny_paths` pelos nomes dos caminhos do OpenAPI.

    Args:
        templates: Caminhos do OpenAPI.
        prefix: Caminho do endereço base.
        keep: Padrões que a sugestão não pode negar, porque o teste precisa deles (o login).

    Returns:
        Os padrões a negar, sem repetição, na ordem do documento.
    """
    suggested: dict[str, None] = {}
    for template in templates:
        if not _is_dangerous(template):
            continue
        pattern = to_scope_pattern(template, prefix)
        if pattern is not None and pattern not in keep:
            suggested[pattern] = None
    return tuple(suggested)
