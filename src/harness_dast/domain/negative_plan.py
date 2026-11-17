"""Plano do teste negativo: quais campos mexer, com qual classe, em que ordem (ADR 0051).

O pedido válido vem do `exchanges.json` do `probe`; o que é proibido vem do `Operation` do
OpenAPI da mesma operação. Mexe-se só em parâmetro de consulta e em campo de primeiro nível de
corpo JSON de `POST`, `PUT` e `PATCH`, UM campo por pedido. A escolha é determinística: por
operação, os campos na ordem do esquema e a classe de maior prioridade primeiro (depois uma
segunda passada); entre operações, rodízio, leituras antes de escritas. O orçamento corta o
excesso e o corte vai para `not_tested`. Escrita só com `allow_writes`; `DELETE` nunca. Este
módulo é puro.

Passa de 300 linhas de propósito: o caso, a extração de campos (consulta e corpo), a ordem em
rodadas e o orçamento se referem uns aos outros; separá-los criaria importação circular.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dc_field
from itertools import zip_longest
from typing import Final
from urllib.parse import parse_qsl, urlsplit

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import JsonValue, Schema, flatten_schema
from harness_dast.domain.authz.sensitive import classify_field_name
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.negative_config import NegativeConfig
from harness_dast.domain.negative_result import Location, NegativeNotTested
from harness_dast.domain.negative_values import (
    CLASS_ORDER,
    CaseClass,
    Proposal,
    propose,
    propose_missing,
)
from harness_dast.domain.probe_exchange import ExchangeRecord

READ_METHODS: Final = frozenset({"GET"})
WRITE_METHODS: Final = frozenset({"POST", "PUT", "PATCH"})
SUPPORTED_METHODS: Final = READ_METHODS | WRITE_METHODS
WRITES_NOT_AUTHORIZED: Final = "writes_not_authorized"


@dataclass(frozen=True)
class NegativeCase:
    """Um pedido do teste: o pedido válido do `probe` com UM campo alterado.

    Attributes:
        exchange: O pedido que o `probe` provou.
        location: `query` ou `body`.
        field: NOME do campo alterado.
        case_class: Classe do valor.
        declared: Limite declarado no OpenAPI.
        value: Valor a enviar; fora do `repr` para nunca chegar a log nem a mensagem.
        remove: O campo é removido em vez de receber `value`.
    """

    exchange: ExchangeRecord = dc_field(repr=False)
    location: Location
    field: str
    case_class: CaseClass
    declared: str
    value: JsonValue = dc_field(repr=False)
    remove: bool = False

    @property
    def key(self) -> tuple[str, str, str]:
        """Identifica a operação do caso: (`operation_id`, método, modelo de caminho)."""
        return (self.exchange.operation_id, self.exchange.method.upper(), self.exchange.path)

    def __post_init__(self) -> None:
        """Recusa método fora de GET, POST, PUT e PATCH (`DELETE` nunca)."""
        if self.exchange.method.upper() not in SUPPORTED_METHODS:
            raise ConfigError(
                "O teste negativo só repete GET, POST, PUT e PATCH; DELETE nunca.",
                hint="Isto é uma regra do código; remova o pedido do plano.",
            )


@dataclass(frozen=True)
class NegativePlan:
    """O que o teste vai enviar e o que ficou sem teste.

    Attributes:
        cases: Casos, na ordem em que serão enviados.
        not_tested: Operações e casos sem teste, com o motivo.
    """

    cases: tuple[NegativeCase, ...]
    not_tested: tuple[NegativeNotTested, ...]


@dataclass
class _Found:
    """Candidatos de um pedido: propostas por campo e o que não se confirmou."""

    per_field: list[list[NegativeCase]] = dc_field(default_factory=list)
    unconfirmable: int = 0

    def add(
        self, name: str, location: Location, proposals: Sequence[Proposal], ex: ExchangeRecord
    ) -> None:
        """Acrescenta as propostas de um campo, na ordem de prioridade."""
        cases = [
            NegativeCase(ex, location, name, p.case_class, p.declared, p.value, p.remove)
            for p in proposals
        ]
        if cases:
            self.per_field.append(cases)


def _note(exchange: ExchangeRecord, reason: str, message: str) -> NegativeNotTested:
    return NegativeNotTested(
        operation_id=exchange.operation_id,
        method=exchange.method.upper(),
        path=exchange.path,
        reason=reason,
        message=message,
    )


def _composite(schema: Schema) -> bool:
    return bool(schema.one_of or schema.any_of)


def _flat(schema: Schema) -> Schema | None:
    """Esquema achatado e utilizável, ou `None` (composição ambígua, nó cortado, só leitura)."""
    if _composite(schema):
        return None
    try:
        flat = flatten_schema(schema)
    except ConfigError:
        return None
    if flat.truncated or flat.read_only:
        return None
    return flat


def _proposals(
    schema: Schema, found: _Found, *, in_query: bool, disabled: frozenset[CaseClass]
) -> list[Proposal]:
    """Propostas de um campo escalar na ordem de prioridade (sem `missing_required`)."""
    chosen: list[Proposal] = []
    for case_class in CLASS_ORDER:
        if case_class in disabled or case_class == "missing_required":
            continue
        outcome = propose(schema, case_class, in_query=in_query)
        if outcome == "unconfirmable":
            found.unconfirmable += 1
        elif isinstance(outcome, Proposal):
            chosen.append(outcome)
    return chosen


def _ordered(proposals: list[Proposal], missing: Proposal | None) -> list[Proposal]:
    """Põe `missing_required` na posição da prioridade (logo depois de `wrong_type`)."""
    if missing is None:
        return proposals
    merged = [*proposals, missing]
    return sorted(merged, key=lambda item: CLASS_ORDER.index(item.case_class))


def _query_fields(
    exchange: ExchangeRecord, operation: Operation, disabled: frozenset[CaseClass], found: _Found
) -> None:
    pairs = parse_qsl(urlsplit(exchange.target).query, keep_blank_values=True)
    counts: dict[str, int] = {}
    for name, _ in pairs:
        counts[name] = counts.get(name, 0) + 1
    for parameter in operation.parameters:
        name = parameter.name
        if parameter.location != "query" or counts.get(name) != 1:
            continue
        if classify_field_name(name) == "secret":
            continue
        schema = _flat(parameter.value_schema)
        if schema is None:
            continue
        proposals = _proposals(schema, found, in_query=True, disabled=disabled)
        missing = None
        if parameter.required and "missing_required" not in disabled:
            container = Schema(type="object", required=(name,))
            outcome = propose_missing(container, {name: "x"}, name)
            missing = outcome if isinstance(outcome, Proposal) else None
        found.add(name, "query", _ordered(proposals, missing), exchange)


def _body_schema(operation: Operation) -> Schema | None:
    if operation.request_body is None:
        return None
    media = operation.request_body.preferred()
    if media is None or media.body_schema is None:
        return None
    return _flat(media.body_schema)


def _body_fields(
    exchange: ExchangeRecord,
    operation: Operation,
    body: dict[str, JsonValue],
    config: NegativeConfig,
    username_field: str | None,
    found: _Found,
) -> None:
    container = _body_schema(operation)
    if container is None:
        return
    method = exchange.method.upper()
    disabled = frozenset(config.disabled_classes)
    for name, raw in container.properties.items():
        skipped = (
            name not in body
            or name in exchange.omitted_fields
            or classify_field_name(name) == "secret"
            or (method != "POST" and name == username_field)
        )
        schema = None if skipped else _flat(raw)
        if schema is None:
            continue
        proposals = _proposals(schema, found, in_query=False, disabled=disabled)
        missing = None
        if method in {"POST", "PUT"} and "missing_required" not in disabled:
            outcome = propose_missing(container, body, name)
            missing = outcome if isinstance(outcome, Proposal) else None
            if outcome == "unconfirmable":
                found.unconfirmable += 1
        found.add(name, "body", _ordered(proposals, missing), exchange)


def _parse_body(exchange: ExchangeRecord) -> dict[str, JsonValue] | None:
    if exchange.body is None:
        return None
    try:
        parsed: JsonValue = json.loads(exchange.body)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _omitted_required(exchange: ExchangeRecord, operation: Operation) -> bool:
    """A linha de base perdeu um campo obrigatório (removido por nome de segredo)."""
    if not exchange.omitted_fields:
        return False
    schema = _body_schema(operation)
    required = frozenset(schema.required) if schema is not None else frozenset()
    return any(name in required for name in exchange.omitted_fields)


def _unsupported_body(exchange: ExchangeRecord, operation: Operation) -> bool:
    """Escrita cujo corpo o teste não sabe alterar (multipart, formulário, ausente, não objeto)."""
    if exchange.multipart is not None:  # corpo multipart (ADR 0052): só o resumo foi gravado
        return True
    if exchange.body is None:
        return operation.request_body is not None
    return _parse_body(exchange) is None


def _rounds(per_field: list[list[NegativeCase]], limit: int) -> tuple[list[NegativeCase], int]:
    """Casos da operação: a 1ª classe de cada campo, depois a 2ª etc.; devolve também o corte."""
    ordered = [case for batch in zip_longest(*per_field) for case in batch if case is not None]
    return ordered[:limit], max(len(ordered) - limit, 0)


def _interleave(groups: list[list[NegativeCase]]) -> list[NegativeCase]:
    return [case for batch in zip_longest(*groups) for case in batch if case is not None]


def plan_negative(
    exchanges: Sequence[ExchangeRecord],
    operations: Mapping[str, Operation],
    config: NegativeConfig,
    *,
    max_requests: int,
    username_field: str | None = None,
    only: frozenset[str] = frozenset(),
    infrastructure: frozenset[str] = frozenset(),
) -> NegativePlan:
    """Planeja os casos do teste negativo.

    Args:
        exchanges: Pedidos do `probe` (`exchanges.json`).
        operations: Operações do OpenAPI por identificador.
        config: Bloco `negative` do perfil.
        max_requests: Teto de envios do estágio (já reduzido por `--max-requests`); o plano
            nunca tem mais casos que isso.
        username_field: `auth.username_field` (não se altera em `PUT` e `PATCH`).
        only: Operações escolhidas por `--only`; vazio = todas.
        infrastructure: Caminhos de login, saúde e preparação: ficam sem teste
            (`infrastructure_path`).

    Returns:
        Os casos, em ordem de envio, e o que ficou sem teste.
    """
    notes: list[NegativeNotTested] = []
    reads: list[list[NegativeCase]] = []
    writes: list[list[NegativeCase]] = []
    for exchange in exchanges:
        method = exchange.method.upper()
        if method not in SUPPORTED_METHODS or (only and exchange.operation_id not in only):
            continue
        if exchange.path in infrastructure:
            notes.append(
                _note(
                    exchange,
                    "infrastructure_path",
                    "caminho de login, saúde ou preparação do perfil: não é operação de negócio",
                )
            )
            continue
        if method in WRITE_METHODS and not config.allow_writes:
            notes.append(
                _note(
                    exchange,
                    WRITES_NOT_AUTHORIZED,
                    "escrita não autorizada pela carta: negative.allow_writes",
                )
            )
            continue
        cases = _exchange_cases(exchange, operations, config, username_field, notes)
        if cases:
            (reads if method in READ_METHODS else writes).append(cases)
    ordered = [*_interleave(reads), *_interleave(writes)]
    budget = max(max_requests, 0)
    kept = ordered[:budget]
    cut = _cut_by_operation(ordered[budget:])
    notes.extend(cut)
    return NegativePlan(cases=tuple(kept), not_tested=tuple(notes))


def _cut_by_operation(cut: list[NegativeCase]) -> list[NegativeNotTested]:
    counts: dict[tuple[str, str, str], int] = {}
    for case in cut:
        key = (case.exchange.operation_id, case.exchange.method.upper(), case.exchange.path)
        counts[key] = counts.get(key, 0) + 1
    return [
        NegativeNotTested(
            operation_id=operation_id,
            method=method,
            path=path,
            reason="budget",
            message=f"{count} caso(s) ficaram de fora do orçamento (negative.max_requests).",
        )
        for (operation_id, method, path), count in counts.items()
    ]


def _exchange_cases(
    exchange: ExchangeRecord,
    operations: Mapping[str, Operation],
    config: NegativeConfig,
    username_field: str | None,
    notes: list[NegativeNotTested],
) -> list[NegativeCase]:
    operation = operations.get(exchange.operation_id)
    if operation is None:
        notes.append(
            _note(exchange, "operation_not_found", "A operação não existe mais no OpenAPI.")
        )
        return []
    method = exchange.method.upper()
    found = _Found()
    disabled = frozenset(config.disabled_classes)
    if method in WRITE_METHODS and _omitted_required(exchange, operation):
        notes.append(
            _note(
                exchange,
                "omitted_required_field",
                "A linha de base perdeu campo obrigatório por nome de segredo (omitted_fields): "
                "o corpo já seria inválido e a rejeição não provaria nada sobre o valor proibido.",
            )
        )
        return []
    if method in WRITE_METHODS and _unsupported_body(exchange, operation):
        notes.append(
            _note(
                exchange,
                "unsupported_body",
                "O pedido de escrita não tem corpo JSON de objeto no exchanges.json "
                "(formulário, multipart ou sem corpo): o teste não sabe alterá-lo.",
            )
        )
        return []
    _query_fields(exchange, operation, disabled, found)
    body = _parse_body(exchange) if method in WRITE_METHODS else None
    if body is not None:
        _body_fields(exchange, operation, body, config, username_field, found)
    cases, cut = _rounds(found.per_field, config.max_cases_per_operation)
    if found.unconfirmable:
        notes.append(
            _note(
                exchange,
                "unconfirmable",
                f"{found.unconfirmable} caso(s) descartados: o esquema não permite confirmar "
                "que o valor é proibido (formato, enum junto de limite, composição).",
            )
        )
    if cut:
        notes.append(
            _note(
                exchange,
                "budget",
                f"{cut} caso(s) ficaram de fora do teto por operação "
                "(negative.max_cases_per_operation).",
            )
        )
    if not cases and not found.unconfirmable:
        notes.append(
            _note(
                exchange,
                "no_testable_field",
                "Nenhum campo de consulta ou de corpo de primeiro nível tem limite que o "
                "contrato declare e o teste consiga violar.",
            )
        )
    return cases
