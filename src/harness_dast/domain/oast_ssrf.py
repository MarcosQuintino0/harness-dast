"""SSRF guiado pelo contrato com retorno fora de banda (V1.12, F3, ADR 0100). Módulo puro.

Só com `scan.oast: true` (que só a carta liga). A partir dos pedidos que o `probe` provou
(`exchanges.json`) e do OpenAPI, escolhe os campos que parecem receber uma URL, troca cada um,
UM por pedido, pela URL de retorno do laboratório com um token único e, depois, compara os
eventos que o serviço de retorno recebeu com os tokens enviados. Retorno com o token certo é
prova de que o alvo fez uma requisição à URL dada: vira achado.

Regras (genéricas, nada específico de produto):

- campo com `format` `uri`, `url`, `uri-reference` ou `iri`; ou
- campo de texto cujo NOME, partido em palavras (`partner_api`, `webhookTarget`), termina em
  `url`, `uri`, `api`, `endpoint`, `href` ou contém `callback` ou `webhook`.

A descrição do OpenAPI não é lida (o carregador não a guarda); fica fora de propósito.

Teto rígido: `SSRF_MAX_REQUESTS` pedidos por execução e `SSRF_MAX_PER_OPERATION` por operação.
`DELETE` nunca; método fora do escopo aprovado não é enviado (`method_not_allowed`).
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dc_field
from itertools import zip_longest
from typing import Final, Literal
from urllib.parse import parse_qsl, quote, urlsplit

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import ApiModel, JsonValue, Schema
from harness_dast.domain.authz.sensitive import classify_field_name
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.request_encoding import join_url
from harness_dast.domain.scan_policy import OAST_CALLBACK_HOST, OAST_CALLBACK_PORT

SSRF_MAX_REQUESTS: Final = 10
"""Teto rígido de pedidos do SSRF guiado por execução do `scan`."""

SSRF_MAX_PER_OPERATION: Final = 3
"""Teto de campos (um pedido por campo) por operação."""

SSRF_PLUGIN_ID: Final = "hdast-oast-ssrf"
SSRF_TITLE: Final = "Server-Side Request Forgery (retorno fora de banda observado)"
SSRF_CWE: Final = 918

URL_FORMATS: Final = frozenset({"uri", "url", "uri-reference", "iri"})
_URL_SUFFIXES: Final = frozenset({"url", "uri", "api", "endpoint", "href"})
_URL_ANYWHERE: Final = frozenset({"callback", "webhook"})
_WORDS: Final = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_WRITE_METHODS: Final = frozenset({"POST", "PUT", "PATCH"})
_METHODS: Final = frozenset({"GET"}) | _WRITE_METHODS
_USER_AGENT_CAP: Final = 80

Reason = Literal["format", "name"]
Where = Literal["query", "body"]


@dataclass(frozen=True)
class SsrfCase:
    """Um pedido do SSRF guiado: o pedido do `probe` com UM campo trocado pela URL de retorno.

    Attributes:
        exchange: O pedido que o `probe` provou.
        location: `query` ou `body`.
        field: Nome do campo trocado.
        reason: Por que o campo parece receber uma URL.
        token: Token único deste campo e desta operação (vai no caminho da URL de retorno).
    """

    exchange: ExchangeRecord = dc_field(repr=False)
    location: Where
    field: str
    reason: Reason
    token: str

    @property
    def operation_id(self) -> str:
        """Operação do pedido."""
        return self.exchange.operation_id

    @property
    def callback_url(self) -> str:
        """URL de retorno deste caso."""
        return callback_url(self.token)


class SsrfSkip(ApiModel):
    """Operação ou campo que ficou sem o teste, com o motivo.

    Attributes:
        operation_id: Operação.
        field: Campo, quando o motivo é do campo.
        reason: `method_not_allowed` (fora do escopo aprovado) ou `budget_exceeded` (teto).
    """

    operation_id: str
    field: str | None = None
    reason: str


@dataclass(frozen=True)
class SsrfPlan:
    """O que será enviado e o que ficou de fora."""

    cases: tuple[SsrfCase, ...]
    skipped: tuple[SsrfSkip, ...]


class OastEvent(ApiModel):
    """Um acesso recebido pelo serviço de retorno (mensagem OAST do ZAP).

    Attributes:
        event_id: Identificador da mensagem na sessão do ZAP.
        path: Caminho pedido (sem consulta).
        at: Horário do evento (ISO 8601, UTC), ou `None` se o ZAP não informou.
        method: Método do acesso.
        user_agent: `User-Agent` do chamador, sanitizado e cortado, ou `None`.
    """

    event_id: int
    path: str
    at: str | None = None
    method: str = "GET"
    user_agent: str | None = None


class SsrfObservation(ApiModel):
    """Retorno correlacionado com um pedido enviado.

    Attributes:
        operation_id: Operação.
        method: Método do pedido enviado.
        path: Modelo de caminho.
        target_path: Caminho concreto enviado (sem consulta).
        field: Campo trocado.
        location: `query` ou `body`.
        token: Token que voltou.
        event: O evento recebido.
        status: Código HTTP da resposta ao pedido enviado, se houve.
    """

    operation_id: str
    method: str
    path: str
    target_path: str
    field: str
    location: Where
    token: str
    event: OastEvent
    status: int | None = None


class SsrfSummary(ApiModel):
    """Resumo do SSRF guiado gravado em `scan.json`.

    Attributes:
        enabled: Ligado (`scan.oast`).
        planned: Pedidos planejados.
        sent: Pedidos enviados (com as retentativas do despachante).
        observed: Retornos correlacionados.
        events_seen: Eventos que o serviço de retorno recebeu durante a etapa.
        cap: Teto de pedidos desta execução.
        observations: Retornos correlacionados, sem valor de campo nem corpo.
        skipped: O que ficou sem o teste.
        note: Observação (parada antecipada, por exemplo).
    """

    enabled: bool = False
    planned: int = 0
    sent: int = 0
    observed: int = 0
    events_seen: int = 0
    cap: int = SSRF_MAX_REQUESTS
    observations: tuple[SsrfObservation, ...] = ()
    skipped: tuple[SsrfSkip, ...] = ()
    note: str | None = None


def callback_url(token: str) -> str:
    """URL de retorno de um token (a ponte do laboratório, ADR 0095)."""
    return f"http://{OAST_CALLBACK_HOST}:{OAST_CALLBACK_PORT}/{token}"


def make_token(seed: int, operation_id: str, location: str, field: str) -> str:
    """Token único por execução, operação, local e campo: 16 hexadecimais derivados da semente."""
    raw = f"hdast-ssrf-v1\0{seed}\0{operation_id}\0{location}\0{field}"
    return "hd" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def field_reason(name: str, schema: Schema) -> Reason | None:
    """Por que o campo parece receber uma URL, ou `None`; nome de segredo nunca é escolhido."""
    if schema.type not in (None, "string") or classify_field_name(name) == "secret":
        return None
    if schema.format is not None and schema.format.lower() in URL_FORMATS:
        return "format"
    words = [item.lower() for item in _WORDS.findall(name)]
    if not words:
        return None
    if words[-1] in _URL_SUFFIXES or any(item in _URL_ANYWHERE for item in words):
        return "name"
    return None


def _query_candidates(
    exchange: ExchangeRecord, operation: Operation
) -> list[tuple[str, Reason, Where]]:
    pairs = parse_qsl(urlsplit(exchange.target).query, keep_blank_values=True)
    counts: dict[str, int] = {}
    for name, _ in pairs:
        counts[name] = counts.get(name, 0) + 1
    found: list[tuple[str, Reason, Where]] = []
    for parameter in operation.parameters:
        if parameter.location != "query" or counts.get(parameter.name) != 1:
            continue
        reason = field_reason(parameter.name, parameter.value_schema)
        if reason is not None:
            found.append((parameter.name, reason, "query"))
    return found


def _body_candidates(
    exchange: ExchangeRecord, operation: Operation
) -> list[tuple[str, Reason, Where]]:
    body = _parse_body(exchange)
    media = operation.request_body.preferred() if operation.request_body else None
    if body is None or media is None or media.body_schema is None:
        return []
    found: list[tuple[str, Reason, Where]] = []
    for name, schema in media.body_schema.properties.items():
        if name not in body or not isinstance(body[name], str) or schema.read_only:
            continue
        reason = field_reason(name, schema)
        if reason is not None:
            found.append((name, reason, "body"))
    return found


def _parse_body(exchange: ExchangeRecord) -> dict[str, JsonValue] | None:
    if exchange.body is None or exchange.multipart is not None:
        return None
    try:
        parsed: JsonValue = json.loads(exchange.body)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def plan_ssrf(
    exchanges: Sequence[ExchangeRecord],
    operations: Mapping[str, Operation],
    *,
    permits: Callable[[str, str], bool],
    seed: int,
    infrastructure: frozenset[str] = frozenset(),
    only: frozenset[str] = frozenset(),
    max_requests: int = SSRF_MAX_REQUESTS,
) -> SsrfPlan:
    """Planeja os pedidos: campos que parecem URL, até `max_requests` e nunca além do teto.

    Args:
        exchanges: Pedidos do `probe` (`exchanges.json`).
        operations: Operações do OpenAPI por identificador.
        permits: `(método, alvo relativo) -> bool`, a decisão do `ScopeGuard` aprovado. Método ou
            caminho fora do escopo não é enviado.
        seed: Semente da execução (os tokens derivam dela).
        infrastructure: Caminhos de login, saúde e preparação (ficam fora).
        only: Operações escolhidas por `--only`; vazio = todas.
        max_requests: Teto pedido; vale no máximo `SSRF_MAX_REQUESTS`.

    Returns:
        Os casos, na ordem de envio (rodízio entre operações), e o que ficou de fora.
    """
    budget = max(0, min(max_requests, SSRF_MAX_REQUESTS))
    skipped: list[SsrfSkip] = []
    groups: list[list[SsrfCase]] = []
    for exchange in exchanges:
        method = exchange.method.upper()
        operation = operations.get(exchange.operation_id)
        unwanted = bool(only) and exchange.operation_id not in only
        if operation is None or method not in _METHODS or unwanted:
            continue
        if exchange.path in infrastructure:
            continue
        found = [*_query_candidates(exchange, operation), *_body_candidates(exchange, operation)]
        if not found:
            continue
        if not permits(method, exchange.target):
            skipped.append(
                SsrfSkip(operation_id=exchange.operation_id, reason="method_not_allowed")
            )
            continue
        groups.append(
            [
                SsrfCase(
                    exchange,
                    location,
                    name,
                    reason,
                    make_token(seed, exchange.operation_id, location, name),
                )
                for name, reason, location in found[:SSRF_MAX_PER_OPERATION]
            ]
        )
    ordered = [case for batch in zip_longest(*groups) for case in batch if case is not None]
    kept, cut = ordered[:budget], ordered[budget:]
    skipped.extend(
        SsrfSkip(operation_id=case.operation_id, field=case.field, reason="budget_exceeded")
        for case in cut
    )
    return SsrfPlan(cases=tuple(kept), skipped=tuple(skipped))


def render_case(case: SsrfCase) -> tuple[str, str | None]:
    """Alvo (caminho e consulta) e corpo do pedido, com o campo do caso trocado pela URL de retorno.

    Returns:
        O alvo relativo à `base_url` e o corpo JSON compacto (ou o original, se o campo é da
        consulta; `None` sem corpo).
    """
    exchange = case.exchange
    url = case.callback_url
    if case.location == "query":
        parts = urlsplit(exchange.target)
        pairs = [
            (name, url if name == case.field else value)
            for name, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        query = "&".join(f"{quote(name, safe='')}={quote(value, safe='')}" for name, value in pairs)
        return (f"{parts.path}?{query}" if query else parts.path), exchange.body
    body = json.loads(exchange.body or "{}")
    body[case.field] = url
    return exchange.target, json.dumps(body, separators=(",", ":"), ensure_ascii=False)


def _event_token(event: OastEvent) -> str:
    return event.path.strip("/")


def correlate(
    cases: Sequence[SsrfCase],
    statuses: Mapping[str, int | None],
    events: Sequence[OastEvent],
    *,
    base_url: str,
) -> tuple[SsrfObservation, ...]:
    """Liga cada evento ao pedido enviado cujo token é o caminho do evento (o primeiro por token).

    Args:
        cases: Casos efetivamente enviados.
        statuses: Código HTTP por token (`None` = sem resposta).
        events: Eventos do serviço de retorno.
        base_url: URL base do ambiente (para o caminho concreto).
    """
    by_token = {case.token: case for case in cases}
    seen: dict[str, SsrfObservation] = {}
    for event in sorted(events, key=lambda item: item.event_id):
        token = _event_token(event)
        case = by_token.get(token)
        if case is None or token in seen:
            continue
        seen[token] = SsrfObservation(
            operation_id=case.operation_id,
            method=case.exchange.method.upper(),
            path=case.exchange.path,
            target_path=urlsplit(join_url(base_url, case.exchange.target)).path,
            field=case.field,
            location=case.location,
            token=token,
            event=event,
            status=statuses.get(token),
        )
    return tuple(seen.values())


def observation_alert(index: int, item: SsrfObservation, *, base_url: str) -> dict[str, str]:
    """Alerta no formato do ZAP (`RawAlert`) para o achado, com a prova do retorno.

    A severidade e a confiança são as propostas pela regra (retorno correlacionado por token
    único: `High`/`High`); nada é gravado do valor do campo original nem de corpo de resposta.
    """
    when = item.event.at or "horário não informado pelo ZAP"
    agent = item.event.user_agent or "não informado"
    proof = (
        f"Evento OAST {item.event.event_id} ({item.event.method} /{item.token}) recebido em "
        f"{when}, via ponte {OAST_CALLBACK_HOST}:{OAST_CALLBACK_PORT} (User-Agent: {agent}); "
        f"o token é o do campo '{item.field}' desta operação."
    )
    return {
        "id": f"oast-{index}",
        "pluginId": SSRF_PLUGIN_ID,
        "alertRef": f"{SSRF_PLUGIN_ID}-1",
        "alert": SSRF_TITLE,
        "cweid": str(SSRF_CWE),
        "wascid": "20",
        "risk": "High",
        "confidence": "High",
        "method": item.method,
        "url": join_url(base_url, item.target_path),
        "param": item.field,
        "attack": callback_url(item.token),
        "evidence": proof,
        "inputVector": "json" if item.location == "body" else "query",
        "messageId": "",
        "sourceMessageId": "",
        "description": (
            f"O campo '{item.field}' recebeu a URL do serviço de retorno do laboratório e o alvo "
            "fez uma requisição a ela: o servidor busca URLs escolhidas por quem chama. " + proof
        ),
        "solution": (
            "Valide o destino contra uma lista de hosts permitidos, recuse endereços internos e "
            "de metadados, não siga redirecionamentos e não devolva a resposta ao chamador."
        ),
    }
