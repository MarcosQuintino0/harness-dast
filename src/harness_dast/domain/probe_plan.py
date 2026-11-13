"""Planejamento do `probe`: quais operações serão enviadas, em que ordem e quais nunca serão.

Regras (contrato):

- Ordem: produtores de `flows.yml` antes dos consumidores (`FlowSpec.execution_order`);
  operações `DELETE` por último, para que um consumidor `DELETE` não apague o que outra
  operação ainda vai ler.
- Escopo: cada operação é conferida contra o `ScopeGuard` com a URL do ambiente e os
  `{marcadores}` trocados por um segmento neutro. Fora do escopo = `skipped_scope`; caminho em
  `deny_paths` = `skipped_denied`. A conferência real, com a URL concreta, acontece de novo
  antes do envio.
- `DELETE` é `skipped_destructive`, salvo com `include_delete` E quando a operação consome
  um valor de `flows.yml` (só se apaga o que foi criado nesta execução).
- `only` seleciona operações e traz junto os produtores de que elas dependem, em qualquer
  nível da cadeia.

Este módulo é puro.
"""

import re
from typing import Literal

from harness_dast.domain.api_model import ApiSpec, Operation
from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.request_encoding import join_url
from harness_dast.domain.scope import OutboundRequest, ScopeGuard

PlanDecision = Literal["send", "skipped_scope", "skipped_denied", "skipped_destructive"]
_PLACEHOLDER = re.compile(r"\{[^{}/]+\}")
_NEUTRAL_SEGMENT = "x"


class PlannedOperation(ApiModel):
    """Uma operação do plano.

    Attributes:
        operation_id: Identificador da operação.
        method: Método HTTP em maiúsculas.
        path: Modelo de caminho do OpenAPI.
        decision: `send` ou o motivo de nunca ser enviada.
        reason: Explicação curta da decisão (sem caminho concreto), ou `None` em `send`.
        depends_on: Produtores (de `flows.yml`) de que esta operação depende, no plano.
        is_producer: Se algum consumidor depende dela.
    """

    operation_id: str
    method: str
    path: str
    decision: PlanDecision
    reason: str | None = None
    depends_on: tuple[str, ...] = ()
    is_producer: bool = False


def probe_url_for(operation: Operation, base_url: str) -> str:
    """URL de conferência de escopo da operação: marcadores trocados por um segmento neutro."""
    return join_url(base_url, _PLACEHOLDER.sub(_NEUTRAL_SEGMENT, operation.path))


def _producers_by_consumer(flows: FlowSpec | None) -> dict[str, tuple[str, ...]]:
    found: dict[str, list[str]] = {}
    for binding in flows.bindings if flows else ():
        for consumer in binding.consumed_by:
            found.setdefault(consumer.operation, []).append(binding.produces.operation)
    return {name: tuple(dict.fromkeys(items)) for name, items in found.items()}


def _select(
    spec: ApiSpec, only: tuple[str, ...], producers: dict[str, tuple[str, ...]]
) -> list[str]:
    ids = [operation.operation_id for operation in spec.operations]
    if not only:
        return ids
    for name in only:
        spec.get_operation(name)
    wanted = set(only)
    pending = list(only)
    while pending:
        # Fecho transitivo: num encadeamento de vários níveis, o produtor do produtor também entra.
        for producer in producers.get(pending.pop(), ()):
            if producer not in wanted:
                wanted.add(producer)
                pending.append(producer)
    return [name for name in ids if name in wanted]


def _scope_decision(
    operation: Operation, guard: ScopeGuard, base_url: str
) -> tuple[PlanDecision, str | None]:
    decision = guard.evaluate(
        OutboundRequest(method=operation.method.upper(), url=probe_url_for(operation, base_url))
    )
    if decision.verdict == "denied_path":
        return "skipped_denied", "O caminho está em scope.deny_paths; nunca é enviado."
    if decision.verdict == "outside_scope":
        return "skipped_scope", "A operação está fora de scope.allow; nunca é enviada."
    return "send", None


def _destructive_decision(
    operation: Operation, *, include_delete: bool, is_consumer: bool
) -> tuple[PlanDecision, str | None]:
    if operation.method != "delete":
        return "send", None
    if include_delete and is_consumer:
        return "send", None
    if include_delete:
        return (
            "skipped_destructive",
            "DELETE só roda sobre recurso criado nesta execução (consumidor em flows.yml).",
        )
    return "skipped_destructive", "DELETE é pulado por padrão; use --include-delete."


def plan_probe(
    spec: ApiSpec,
    flows: FlowSpec | None,
    guard: ScopeGuard,
    base_url: str,
    *,
    include_delete: bool = False,
    only: tuple[str, ...] = (),
) -> tuple[PlannedOperation, ...]:
    """Monta o plano do `probe` (ver as regras no docstring do módulo).

    Raises:
        ConfigError: Se `only` citar uma operação que não existe no OpenAPI (a dica lista
            identificadores válidos).
    """
    producers = _producers_by_consumer(flows)
    selected = _select(spec, only, producers)
    ordered = list(flows.execution_order(selected)) if flows else selected
    by_id = {operation.operation_id: operation for operation in spec.operations}
    ordered.sort(key=lambda name: by_id[name].method == "delete")
    producer_ids = {p for items in producers.values() for p in items}
    return tuple(
        _plan_one(by_id[name], guard, base_url, producers, producer_ids, include_delete, selected)
        for name in ordered
    )


def _plan_one(
    operation: Operation,
    guard: ScopeGuard,
    base_url: str,
    producers: dict[str, tuple[str, ...]],
    producer_ids: set[str],
    include_delete: bool,
    selected: list[str],
) -> PlannedOperation:
    name = operation.operation_id
    decision, reason = _scope_decision(operation, guard, base_url)
    if decision == "send":
        decision, reason = _destructive_decision(
            operation, include_delete=include_delete, is_consumer=name in producers
        )
    return PlannedOperation(
        operation_id=name,
        method=operation.method.upper(),
        path=operation.path,
        decision=decision,
        reason=reason,
        depends_on=tuple(p for p in producers.get(name, ()) if p in selected),
        is_producer=name in producer_ids,
    )


_DESTRUCTIVE_HINTS = re.compile(
    r"(?i)(?:createdb|resetdb|reset|drop|purge|truncate|wipe|populate|seed|init(?:ialize|db)?)"
)


def looks_destructive(operation: Operation) -> bool:
    """Heurística: o nome ou o caminho sugere reiniciar, recriar ou apagar dados do ambiente.

    É só uma dica para o agente propor `deny_paths` (estreitar o escopo); nenhuma decisão do
    harness depende dela.
    """
    return _DESTRUCTIVE_HINTS.search(f"{operation.operation_id} {operation.path}") is not None
