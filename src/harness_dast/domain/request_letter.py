"""Completa a carta `kind: request` com os padrões do pedido mínimo (ADR 0120).

A pessoa responde só quatro perguntas (portões e dono, endereço, força, gravação no ambiente).
Aqui a CLI preenche o resto da carta com a tabela de `request_defaults` e com o escopo tirado
do OpenAPI, de modo que o restante da conferência (`letter_review`) trate a carta completa como
trata qualquer carta: o que o perfil recusa, a carta recusa.

Regras que valem aqui:
- Resposta explícita (origem `carta` ou `pessoa`, com valor) vence o padrão, inclusive para
  desligar. `desconhecido` e campo ausente recebem o padrão. A exceção é `scope.deny_paths`: a
  resposta da pessoa soma à sugestão e nunca a remove.
- O caminho é sempre `strict`; `wide` só vale na carta `kind: letter`, com frase.
- O endereço base vem da resposta da pessoa, nunca do `servers` do OpenAPI.
- As três capacidades de escrita só ligam com a pergunta 4 `true` ou com a chave individual
  explícita; o padrão nunca as liga.
- Os valores padrão entram na carta como resposta `carta` com uma frase que diz de onde vêm
  (`DEFAULT_QUOTE`), para os leitores existentes os aceitarem sem mudar.

Este módulo é puro: o dia de hoje, o fuso e os caminhos do OpenAPI entram por parâmetro.
"""

from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.letter import Answer, Letter, ScopeSection
from harness_dast.domain.letter_collect import INVALID_VALUE, WIDE_NEEDS_LETTER, Collector
from harness_dast.domain.request_answers import default_answer, explicit, flag, pick, text
from harness_dast.domain.request_defaults import (
    DEFAULT_METHODS,
    DEFAULT_TIMEZONE,
    DELETE_METHOD,
    RequestDefault,
)
from harness_dast.domain.request_fill import (
    fill_attack,
    fill_auth,
    fill_authorization,
    fill_limits,
)
from harness_dast.domain.request_paths import allow_patterns, suggest_deny_paths, to_scope_pattern
from harness_dast.domain.urlnorm import default_port, split_request

OPENAPI_UNREADABLE: Final = "OPENAPI_UNREADABLE"
REQUEST_ONLY: Final = "REQUEST_ONLY"
_MAX_PATHS_PER_RULE: Final = 200

LetterKind = Literal["letter", "request"]


class RequestInputs(BaseModel):
    """O que o modo `request` precisa de fora da carta.

    Attributes:
        api_paths: Modelos de caminho do OpenAPI (`/users/{id}`), na ordem do documento;
            `None` quando o arquivo não pôde ser lido.
        api_error: Por que o OpenAPI não foi lido (texto sem conteúdo do arquivo).
        timezone: Nome IANA do fuso da janela padrão.
    """

    model_config = ConfigDict(frozen=True)

    api_paths: tuple[str, ...] | None = None
    api_error: str | None = None
    timezone: str = DEFAULT_TIMEZONE


@dataclass(frozen=True, slots=True)
class _Origin:
    host: str
    scheme: str
    port: int | None
    allow_local: bool
    prefix: str

    @property
    def text(self) -> str:
        port = "" if self.port is None else f":{self.port}"
        return f"{self.scheme}://{self.host}{port}{self.prefix}"


def letter_kind(letter: Letter) -> LetterKind | None:
    """O modo da carta: `letter` se ausente; `None` se o valor não é `letter` nem `request`."""
    if letter.kind is None or letter.kind == "letter":
        return "letter"
    return "request" if letter.kind == "request" else None


def requested_openapi(letter: Letter) -> str | None:
    """O caminho do OpenAPI que a carta informou, se há um; é de onde o modo `request` lê."""
    return text(letter.environment.openapi)


def reject_request_only_keys(c: Collector, letter: Letter) -> None:
    """No modo `letter`, recusa as chaves que só existem no pedido mínimo."""
    keys = (
        ("attack.allow_data_writes", letter.attack.allow_data_writes),
        ("scope.allow_delete", letter.scope.allow_delete),
    )
    for field, answer in keys:
        if answer is not None:
            c.add(
                field,
                REQUEST_ONLY,
                "Esta chave só vale com kind: request (pedido mínimo). Na carta assinada "
                "(kind: letter) cada capacidade exige source: carta e a frase em quote.",
            )


def check_base_url_gate(c: Collector, letter: Letter) -> None:
    """Segundo portão do pedido mínimo: o endereço do ambiente, vindo da pessoa.

    `desconhecido`, ausente ou inválido para o cadastro: o `servers` do OpenAPI nunca vale.
    """
    answer = letter.environment.base_url
    if c.take_text("environment.base_url", answer) is None:
        return
    if _origin(letter.environment.base_url) is None:
        c.add(
            "environment.base_url",
            INVALID_VALUE,
            "Endereço base inválido para a cerca: use http(s)://host[:porta][/prefixo], sem "
            "usuário, consulta nem caractere especial no caminho.",
        )


def fill_request_letter(
    letter: Letter, c: Collector, inputs: RequestInputs, today: date
) -> tuple[Letter, tuple[RequestDefault, ...]]:
    """Devolve a carta completa com os padrões do pedido mínimo e a lista do que foi aplicado.

    Args:
        letter: Carta `kind: request` com os portões já conferidos.
        c: Coletor das pendências.
        inputs: Caminhos do OpenAPI e fuso.
        today: Dia de hoje em UTC (a validade padrão conta a partir dele).

    Returns:
        A carta preenchida e os padrões aplicados, na ordem do cabeçalho. Com pendência no
        coletor, a carta devolvida não deve ser usada.
    """
    if inputs.api_paths is None:
        c.add(
            "environment.openapi",
            OPENAPI_UNREADABLE,
            inputs.api_error
            or "O modo request lê o OpenAPI para montar o escopo, e ele não pôde ser lido.",
        )
        return letter, ()
    applied: list[RequestDefault] = []
    scope = _fill_scope(letter, c, inputs, applied)
    filled = letter.model_copy(
        update={
            "environment": letter.environment.model_copy(
                update={"name": pick(letter.environment.name, "environment.name", applied)}
            ),
            "scope": scope,
            "authorization": fill_authorization(letter, today, inputs.timezone, applied),
            "limits": fill_limits(letter, applied),
            "auth": fill_auth(letter, applied),
            "attack": fill_attack(letter.attack, c, applied),
        }
    )
    return filled, tuple(applied)


def _origin(answer: Answer | None) -> _Origin | None:
    url = text(answer)
    if url is None:
        return None
    try:
        parts = split_request("GET", url)
    except ScopeViolation:
        return None
    base = parts.raw_path.rstrip("/")
    if base and to_scope_pattern(base) is None:
        return None
    port = None if parts.port == default_port(parts.scheme) else parts.port
    return _Origin(
        host=parts.host.text,
        scheme=parts.scheme,
        port=port,
        allow_local=parts.host.is_local,
        prefix=base,
    )


def _fill_scope(
    letter: Letter, c: Collector, inputs: RequestInputs, applied: list[RequestDefault]
) -> ScopeSection:
    scope = letter.scope
    origin = _origin(letter.environment.base_url)
    paths = inputs.api_paths or ()
    if origin is None:  # o portão do endereço já recusou; aqui só falha fechada
        return scope
    login = text(letter.auth.token_path)
    keep = frozenset(
        pattern
        for pattern in (None if login is None else to_scope_pattern(login, origin.prefix),)
        if pattern is not None
    )
    return scope.model_copy(
        update={
            "allow": _fill_allow(letter, c, origin, paths, applied),
            "deny_paths": _fill_deny(letter, origin.prefix, paths, keep, applied),
            "path_mode": _fill_path_mode(scope.path_mode, c, applied),
        }
    )


def _fill_allow(
    letter: Letter,
    c: Collector,
    origin: _Origin,
    templates: tuple[str, ...],
    applied: list[RequestDefault],
) -> Answer | None:
    scope = letter.scope
    delete = flag(c, "scope.allow_delete", scope.allow_delete)
    given = explicit(scope.allow)
    if given is not None:
        if delete:
            c.add(
                "scope.allow_delete",
                INVALID_VALUE,
                "O scope.allow explícito já diz os métodos: tire o allow_delete ou o scope.allow.",
            )
        return given
    patterns, skipped = allow_patterns(templates, origin.prefix)
    if not patterns:
        c.add(
            "environment.openapi",
            OPENAPI_UNREADABLE,
            "O OpenAPI não tem nenhum caminho que a cerca aceite; confira o arquivo.",
        )
        return None
    methods = (*DEFAULT_METHODS, DELETE_METHOD) if delete else DEFAULT_METHODS
    note = (
        f"; {skipped} caminho(s) ficaram de fora (padrão que a cerca não aceita)" if skipped else ""
    )
    applied.append(
        RequestDefault(
            field="scope.allow",
            value=f"{len(patterns)} caminho(s) do OpenAPI em {origin.text}, métodos "
            + ", ".join(methods)
            + note,
            reason="todos os caminhos do OpenAPI, com {x} como curinga; o DELETE só entra "
            "quando a pessoa pede",
        )
    )
    return default_answer([_rule(origin, chunk, methods) for chunk in _chunks(patterns)])


def _chunks(patterns: tuple[str, ...]) -> list[tuple[str, ...]]:
    size = _MAX_PATHS_PER_RULE
    return [patterns[start : start + size] for start in range(0, len(patterns), size)]


def _rule(
    origin: _Origin, patterns: tuple[str, ...], methods: tuple[str, ...]
) -> dict[str, object]:
    rule: dict[str, object] = {"host": origin.host, "scheme": origin.scheme}
    if origin.port is not None:
        rule["port"] = origin.port
    if origin.allow_local:
        rule["allow_local"] = True
    rule["paths"] = list(patterns)
    rule["methods"] = list(methods)
    return rule


def _fill_deny(
    letter: Letter,
    prefix: str,
    templates: tuple[str, ...],
    keep: frozenset[str],
    applied: list[RequestDefault],
) -> Answer | None:
    """Sugestão da CLI somada às respostas da pessoa: a lista dela nunca a remove."""
    person = explicit(letter.scope.deny_paths)
    if person is not None and not _is_text_list(person.value):
        return person
    suggested = suggest_deny_paths(templates, prefix, keep)
    if suggested:
        applied.append(
            RequestDefault(
                field="scope.deny_paths",
                value=suggested,
                reason="sugestão por nome (recuperação e troca de senha, logout, exclusão de "
                "conta e administração); a pessoa soma caminhos, nunca tira",
            )
        )
    extra = [] if person is None else list(_texts(person.value))
    return default_answer(list(dict.fromkeys([*suggested, *extra])))


def _is_text_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _texts(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _fill_path_mode(answer: Answer | None, c: Collector, applied: list[RequestDefault]) -> Answer:
    given = explicit(answer)
    if given is None:
        return pick(None, "scope.path_mode", applied)
    if given.value != "strict":
        code = WIDE_NEEDS_LETTER if given.value == "wide" else INVALID_VALUE
        c.add(
            "scope.path_mode",
            code,
            "No pedido mínimo o caminho é sempre strict. O modo amplo só vale numa carta "
            "assinada (kind: letter) com a frase do dono do produto.",
        )
    return default_answer("strict")
