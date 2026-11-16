"""Aplica receitas validadas apenas a candidatos e leituras já provados no plano atual."""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import flatten_schema
from harness_dast.domain.authz_compare import is_success_status
from harness_dast.domain.authz_plan import Planned
from harness_dast.domain.authz_plan_mass import MassTask
from harness_dast.domain.knowledge import KnowledgeEffect
from harness_dast.domain.probe_exchange import ExchangeRecord


def apply_effect_recipes(
    plan: Planned[MassTask],
    exchanges: Sequence[ExchangeRecord],
    operations: Mapping[str, Operation],
    recipes: Sequence[KnowledgeEffect],
    public: frozenset[str],
    infrastructure: frozenset[str],
) -> Planned[MassTask]:
    """Adiciona leitura provada sem remover candidatos, ampliar teto ou criar escrita."""
    tasks: list[MassTask] = []
    for task in plan.tasks:
        if task.read is not None:
            tasks.append(task)
            continue
        readers = [
            _reader_for(
                task, candidate.name, exchanges, operations, recipes, public, infrastructure
            )
            for candidate in task.candidates
        ]
        if not any(readers):
            tasks.append(task)
            continue
        selected = tuple(
            (candidate.name, reader)
            for candidate, reader in zip(task.candidates, readers, strict=True)
            if reader is not None
        )
        tasks.append(replace(task, candidate_readers=selected))
    return Planned(tuple(tasks), plan.not_tested)


def _reader_for(
    task: MassTask,
    field: str,
    exchanges: Sequence[ExchangeRecord],
    operations: Mapping[str, Operation],
    recipes: Sequence[KnowledgeEffect],
    public: frozenset[str],
    infrastructure: frozenset[str],
) -> ExchangeRecord | None:
    write = operations.get(task.exchange.operation_id)
    if write is None or write.method.upper() != task.exchange.method.upper():
        return None
    ids = {
        recipe.read_operation
        for recipe in recipes
        if recipe.write_operation == task.exchange.operation_id
        and recipe.account == task.exchange.account
        and field in recipe.fields
    }
    matches = [
        read
        for read in exchanges
        if read.operation_id in ids
        and read.operation_id not in public
        and read.path not in infrastructure
        and read.method == "GET"
        and is_success_status(read.status)
        and read.account == task.exchange.account
        and _compatible(task, read, operations.get(read.operation_id), field)
    ]
    unique = {(read.operation_id, read.path, read.target): read for read in matches}
    return next(iter(unique.values())) if len(unique) == 1 else None


def _compatible(
    task: MassTask, read: ExchangeRecord, operation: Operation | None, field: str
) -> bool:
    if operation is None or operation.method != "get" or operation.path != read.path:
        return False
    if task.created:
        tail = read.path.rsplit("/", 1)[-1]
        if not (tail.startswith("{") and tail.endswith("}")):
            return False
    elif read.target != task.exchange.target:
        return False
    for response in operation.success_responses:
        if response.body_schema is None:
            continue
        schema = flatten_schema(response.body_schema)
        if schema.type == "array" and schema.items is not None:
            schema = flatten_schema(schema.items)
        if not schema.truncated and field in schema.properties:
            return True
    return False
