"""Tentativas repetidas sem bloqueio em autenticação e verificação (V1.12, F5b, ADR 0101). Puro.

Só com `extra_checks.allow_rate_tests: true` (que só a carta liga). A regra é genérica, derivada
do contrato: um `POST` sem parâmetro de caminho, com corpo JSON, cujo caminho tem palavra de
autenticação ou verificação (`login`, `otp`, `verify`, `mfa`, `password`...) e cujo corpo tem um
campo de "palpite" (`otp`, `pin`, `password`, `code` de verificação...). A CLI manda no máximo
`ATTEMPTS_PER_OPERATION` pedidos com um valor ERRADO por construção e do tipo certo (dígitos num
campo de código numérico, do tamanho que o contrato ou o exemplo indica; senha sintética), com o
identificador da conta de teste da carta, e para no primeiro sinal de limite: `429`,
`Retry-After`, bloqueio de conta, mudança de resposta ou texto de bloqueio. Só conclui "sem limite"
quando as tentativas recebem rejeição de verdade (4xx de credencial ou código errado, estável):
`5xx` na primeira resposta é inconclusivo (o servidor quebrou, não rejeitou). Passadas todas as
tentativas com rejeição estável e sem sinal, é achado de severidade média. Nunca é a senha real e
nunca é outra conta além das de teste.

Operações que trocam ou cadastram credencial (`change`, `set`, `update`, `register`, `signup`,
campos `new_*`, `current_*`, `old_*`, `confirm_*` de senha) ficam de fora: um 2xx numa delas
mudaria a senha da conta de teste. Se uma operação escolhida devolver 2xx, o fato fica registrado
como possível mudança de estado (`possible_state_change`).

Teto rígido: `ATTEMPTS_PER_OPERATION` por operação e `ATTEMPT_MAX_OPERATIONS` operações por
execução. O caminho de login do perfil (`auth.token_path`) fica de fora: a conta que roda a
varredura não pode ser bloqueada por este teste.
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import JsonValue, Schema, effective_type, flatten_schema
from harness_dast.domain.authz.sensitive import field_words
from harness_dast.domain.extra_check_result import (
    RATE_ATTEMPTS_PLUGIN,
    ExtraSkip,
    build_alert,
)
from harness_dast.domain.probe_policy import TRANSPORT_FAILURE_STATUSES
from harness_dast.domain.request_encoding import join_url

ATTEMPTS_PER_OPERATION: Final = 20
"""Teto rígido de pedidos por operação."""

ATTEMPT_MAX_OPERATIONS: Final = 3
"""Teto de operações testadas por execução."""

ATTEMPT_MAX_REQUESTS: Final = ATTEMPTS_PER_OPERATION * ATTEMPT_MAX_OPERATIONS
"""Teto de pedidos de tentativas por execução."""

ATTEMPTS_CWE: Final = 307
ATTEMPTS_TITLE: Final = (
    "Tentativas repetidas sem bloqueio em operação de autenticação ou verificação"
)

PATH_WORDS: Final = frozenset(
    {
        "login",
        "signin",
        "auth",
        "authenticate",
        "authentication",
        "otp",
        "verify",
        "verification",
        "mfa",
        "2fa",
        "totp",
        "token",
        "password",
        "passwd",
        "reset",
        "session",
        "unlock",
        "activate",
        "confirm",
    }
)
"""Palavras do caminho que marcam autenticação ou verificação."""

STATE_CHANGE_WORDS: Final = frozenset(
    {"change", "set", "update", "register", "signup", "create", "edit", "new"}
)
"""Palavras do caminho de operações que trocam ou cadastram credencial (ficam de fora)."""

_STATE_FIELD_PREFIX: Final = frozenset({"new", "current", "old"})
_NUMERIC_GUESS: Final = frozenset({"otp", "pin", "passcode", "totp", "mfa"})
_SECRET_GUESS: Final = frozenset({"password", "passwd", "pwd"})
_CODE_PREFIX: Final = frozenset(
    {
        "otp",
        "verification",
        "verify",
        "auth",
        "sms",
        "security",
        "confirmation",
        "confirm",
        "reset",
        "mfa",
        "login",
        "access",
        "activation",
    }
)
_IDENTITY_WORDS: Final = frozenset(
    {"email", "username", "user", "login", "phone", "mobile", "identifier", "account"}
)
_WRONG_TEXT: Final = "hdastwrong"  # texto errado de campo não numérico
_WRONG_SECRET: Final = "Hdast#Wrong-0"  # noqa: S105  # valor sintético errado de propósito
_WRONG_OTHER: Final = "hdast-synthetic"
_PATH_SPLIT: Final = re.compile(r"[^A-Za-z0-9]+")
_PARAM: Final = re.compile(r"\{[^{}]*\}")
_BODY_WINDOW: Final = 4096
_LOCKOUT_TEXT: Final = (
    "locked",
    "too many",
    "rate limit",
    "attempts exceeded",
    "number of attempts",
    "try again later",
    "temporarily blocked",
    "account blocked",
    "captcha",
    "throttl",
)
_USELESS_STATUSES: Final = frozenset({404, 405, 410, 415, 422})
_LOCKED_STATUSES: Final = frozenset({423, 429})


@dataclass(frozen=True)
class AttemptCase:
    """Uma operação de autenticação ou verificação e o corpo errado a repetir.

    Attributes:
        operation_id: Operação.
        path: Modelo de caminho (sem parâmetros).
        guess_field: Campo de palpite (o que a repetição erra).
        body: Corpo JSON compacto, com o valor errado, sem segredo real.
    """

    operation_id: str
    path: str
    guess_field: str
    body: str = ""


@dataclass(frozen=True)
class AttemptPlan:
    """O que será enviado e o que ficou de fora."""

    cases: tuple[AttemptCase, ...]
    skipped: tuple[ExtraSkip, ...]


@dataclass(frozen=True)
class AttemptReply:
    """Uma resposta reduzida ao que o veredito usa (o corpo nunca é guardado)."""

    status: int | None
    retry_after: str | None
    text: str


def path_words(path: str) -> frozenset[str]:
    """Palavras (minúsculas) dos segmentos do caminho: `check-otp` vira `check` e `otp`."""
    words: set[str] = set()
    for segment in path.split("/"):
        words.update(item for item in _PATH_SPLIT.split(segment.lower()) if item)
    return frozenset(words)


def guess_kind(name: str) -> str | None:
    """`numeric`, `secret` ou `code` se o NOME é um campo de palpite; senão `None`."""
    words = field_words(name)
    if not words:
        return None
    if words[-1] in _NUMERIC_GUESS or any(word in _NUMERIC_GUESS for word in words):
        return "numeric"
    if any(word in _SECRET_GUESS for word in words):
        return "secret"
    if words[-1] == "code" and (len(words) == 1 or bool(set(words[:-1]) & _CODE_PREFIX)):
        return "code"
    return None


def _changes_credential(name: str) -> bool:
    """Campo de troca ou cadastro de credencial (`new_password`, `current_password`...)."""
    words = field_words(name)
    if not words:
        return False
    if words[0] in _STATE_FIELD_PREFIX:
        return True
    return words[0] == "confirm" and words[-1] in _SECRET_GUESS | {"secret"}


def _is_identity(name: str) -> bool:
    words = field_words(name)
    return bool(words) and words[-1] in _IDENTITY_WORDS


_DIGITS: Final = "0987654321"
_PATTERN_DIGITS: Final = re.compile(r"\d|\[0-9")
_PATTERN_SIZE: Final = re.compile(r"\{(\d+)(?:,(\d+))?\}")
_DEFAULT_SIZE: Final = 6
_MAX_DEFAULT_SIZE: Final = 8


def _is_digits(kind: str, schema: Schema) -> bool:
    """O valor errado deve ser feito de dígitos: campo numérico, padrão ou exemplo numéricos."""
    if kind == "numeric":
        return True
    if schema.pattern is not None and _PATTERN_DIGITS.search(schema.pattern):
        return True
    return isinstance(schema.example, str) and schema.example.isdigit()


def _wrong_size(schema: Schema) -> int:
    """Tamanho do valor errado: `pattern`, exemplo ou `minLength`/`maxLength`; senão 6 (até 8).

    Sempre dentro de `minLength` e `maxLength`.
    """
    size = 0
    if schema.pattern is not None and (found := _PATTERN_SIZE.search(schema.pattern)):
        size = int(found.group(2) or found.group(1))
    elif isinstance(schema.example, str) and schema.example:
        size = len(schema.example)
    elif schema.min_length is not None and schema.min_length == schema.max_length:
        size = schema.min_length
    else:
        size = min(schema.max_length or _DEFAULT_SIZE, _MAX_DEFAULT_SIZE)
    size = max(size, schema.min_length or 1)
    return min(size, schema.max_length) if schema.max_length else size


def _wrong_text(kind: str, schema: Schema) -> str:
    """Texto errado por construção, determinístico e do formato do campo (ADR 0101)."""
    size = _wrong_size(schema)
    base = _DIGITS if _is_digits(kind, schema) else _WRONG_TEXT
    value = (base * size)[:size]
    if isinstance(schema.example, str) and value == schema.example:
        value = ("1" if base == _DIGITS else "x") + value[1:]
    return value


def _wrong_value(kind: str, schema: Schema) -> JsonValue | None:
    """Valor errado por construção para o campo de palpite, ou `None` se o tipo não serve.

    Respeita o tipo e o formato do contrato: um código numérico recebe dígitos (nunca letras, que o
    servidor trata como erro de formato e devolve `5xx`), do tamanho de `minLength`, `maxLength`,
    `pattern` ou do exemplo. Um número fica abaixo do mínimo declarado.
    """
    flat = flatten_schema(schema)
    kind_of = effective_type(flat)
    if kind_of == "integer" or kind_of == "number":
        low = flat.minimum if flat.minimum is not None else 0
        return int(low) - 1
    if kind_of not in (None, "string"):
        return None
    if kind == "secret":
        return _WRONG_SECRET
    return _wrong_text(kind, flat)


def _other_value(name: str, schema: Schema, identity: str | None) -> JsonValue | None:
    flat = flatten_schema(schema)
    kind_of = effective_type(flat)
    if kind_of == "boolean":
        return False
    if kind_of in ("integer", "number"):
        return int(flat.minimum) if flat.minimum is not None else 0
    if kind_of in (None, "string"):
        if flat.format == "email" and identity is not None:
            return identity
        return _WRONG_OTHER
    return None


def build_attempt_body(
    schema: Schema, *, identity: str | None
) -> tuple[str, str] | ExtraSkip | None:
    """Corpo errado e o campo de palpite; ou o motivo de pular; ou `None` sem campo de palpite.

    Entram o identificador da conta de teste (campos `email`, `username`...), o valor errado nos
    campos de palpite e um valor sintético fixo nos demais campos obrigatórios. Corpo com campo
    obrigatório de tipo composto não é montado (`unsupported_body`) e corpo com campo de troca de
    credencial (`new_password`...) é pulado (`state_changing_operation`).
    """
    flat = flatten_schema(schema)
    guesses = [(name, kind) for name in flat.properties if (kind := guess_kind(name)) is not None]
    if not guesses:
        return None
    if any(_changes_credential(name) for name in flat.properties):
        return ExtraSkip(subject="", reason="state_changing_operation")
    primary = next((name for name, kind in guesses if kind != "secret"), guesses[0][0])
    body: dict[str, JsonValue] = {}
    for name, prop in flat.properties.items():
        kind = guess_kind(name)
        if kind is not None:
            value = _wrong_value(kind, prop)
        elif _is_identity(name):
            if identity is None:
                return ExtraSkip(subject="", reason="no_test_identity")
            value = identity
        elif name in flat.required:
            value = _other_value(name, prop, identity)
        else:
            continue
        if value is None:
            return ExtraSkip(subject="", reason="unsupported_body")
        body[name] = value
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False), primary


def plan_attempts(
    operations: Mapping[str, Operation],
    *,
    identity: str | None,
    permits: Callable[[str, str], bool],
    infrastructure: frozenset[str] = frozenset(),
    only: frozenset[str] = frozenset(),
    max_operations: int = ATTEMPT_MAX_OPERATIONS,
) -> AttemptPlan:
    """Escolhe as operações de autenticação ou verificação pelo contrato.

    Args:
        operations: Operações do OpenAPI por identificador (a ordem do contrato decide).
        identity: Identificador da conta de teste (usuário da carta), ou `None`.
        permits: `(método, alvo relativo) -> bool`, a decisão do `ScopeGuard` aprovado.
        infrastructure: Caminhos de login, saúde e preparação (ficam fora).
        only: Operações escolhidas por `--only`; vazio = todas.
        max_operations: Teto pedido; vale no máximo `ATTEMPT_MAX_OPERATIONS`.
    """
    budget = max(0, min(max_operations, ATTEMPT_MAX_OPERATIONS))
    cases: list[AttemptCase] = []
    skipped: list[ExtraSkip] = []
    for operation in operations.values():
        media = operation.request_body.preferred() if operation.request_body else None
        words = path_words(operation.path)
        if (
            operation.method.lower() != "post"
            or _PARAM.search(operation.path)
            or operation.path in infrastructure
            or (only and operation.operation_id not in only)
            or not (words & PATH_WORDS)
            or media is None
            or media.body_schema is None
            or "json" not in media.media_type.lower()
        ):
            continue
        built = build_attempt_body(media.body_schema, identity=identity)
        if built is None:
            continue
        if words & STATE_CHANGE_WORDS:
            skipped.append(
                ExtraSkip(subject=operation.operation_id, reason="state_changing_operation")
            )
        elif isinstance(built, ExtraSkip):
            skipped.append(built.model_copy(update={"subject": operation.operation_id}))
        elif not permits("POST", operation.path):
            skipped.append(ExtraSkip(subject=operation.operation_id, reason="not_allowed_by_scope"))
        elif len(cases) >= budget:
            skipped.append(ExtraSkip(subject=operation.operation_id, reason="budget_exceeded"))
        else:
            cases.append(AttemptCase(operation.operation_id, operation.path, built[1], built[0]))
    return AttemptPlan(cases=tuple(cases), skipped=tuple(skipped))


def reply_text(body: bytes) -> str:
    """Início do corpo em minúsculas, só para procurar texto de bloqueio (nunca é gravado)."""
    return body[:_BODY_WINDOW].decode("utf-8", errors="ignore").lower()


def first_reply_problem(reply: AttemptReply) -> str | None:
    """Por que a primeira resposta não permite o teste, ou `None`.

    Só a rejeição de verdade (4xx de credencial ou código errado) permite concluir "sem limite".
    `unexpected_success` (2xx) para na hora: o valor errado foi aceito, assunto de outra checagem,
    e a operação pode ter mudado estado (`possible_state_change`). `server_error_http_5xx` é o
    servidor quebrando, não rejeitando: inconclusivo, nunca achado.
    """
    status = reply.status
    if status is None:
        return "no_response"
    if 200 <= status < 300:
        return "unexpected_success"
    if status in _USELESS_STATUSES:
        return f"not_testable_http_{status}"
    if status in TRANSPORT_FAILURE_STATUSES or 300 <= status < 400:
        return f"not_testable_http_{status}"
    if status >= 500:
        return f"server_error_http_{status}"
    return None


def limit_signal(reply: AttemptReply, first_status: int | None) -> str | None:
    """Sinal de limite numa resposta, ou `None`.

    Sinais: `429` ou `423`; `Retry-After`; mudança do código em relação ao da primeira resposta
    (bloqueio de conta, `503` de tentativas excedidas...); texto de bloqueio no corpo.
    """
    if reply.status in _LOCKED_STATUSES:
        return f"http_{reply.status}"
    if reply.retry_after:
        return "retry_after"
    if first_status is not None and reply.status != first_status:
        return f"status_changed_to_{reply.status}"
    if any(word in reply.text for word in _LOCKOUT_TEXT):
        return "lockout_text"
    return None


def attempts_alert(
    index: int, case: AttemptCase, attempts: int, status: int | None, *, base_url: str
) -> dict[str, str]:
    """Alerta do achado: severidade média, com a contagem das tentativas na evidência."""
    evidence = (
        f"{attempts} tentativas seguidas com valor errado e sintético no campo "
        f"'{case.guess_field}' "
        f"(sempre HTTP {status}), sem 429, sem Retry-After, sem bloqueio de conta e sem mudança "
        "na resposta."
    )
    return build_alert(
        ident=f"rate-attempts-{index}",
        plugin_id=RATE_ATTEMPTS_PLUGIN,
        title=ATTEMPTS_TITLE,
        cwe=ATTEMPTS_CWE,
        risk="Medium",
        confidence="Medium",
        method="POST",
        url=join_url(base_url, case.path),
        param=case.guess_field,
        evidence=evidence,
        description=(
            "A operação de autenticação ou verificação aceitou tentativas repetidas sem nenhum "
            "sinal de limite: um atacante pode adivinhar o valor por força bruta. A CLI parou "
            "no teto de tentativas (o teste nunca é uma negação de serviço). " + evidence
        ),
        solution=(
            "Limite as tentativas por conta e por origem (429 com Retry-After, atraso crescente "
            "ou bloqueio temporário), invalide o código após poucas falhas e registre o excesso."
        ),
    )
