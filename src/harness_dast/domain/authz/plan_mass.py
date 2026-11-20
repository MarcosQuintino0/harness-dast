"""Plano da atribuição em massa: operações de escrita, leitor do efeito e candidatos (ADR 0040).

Escolhe, entre os pedidos que o `probe` já provou com sucesso, os `PUT`, `PATCH` e `POST` com
corpo JSON (objeto) que o perfil manda testar (`authz.mass_assignment_methods`), liga cada um ao
`GET` que mostra o efeito e junta os candidatos de campo (declarados e derivados do OpenAPI).
Nunca `DELETE`. O teto da execução (`MAX_MASS_REQUESTS`) vale no plano e de novo no envio.
Este módulo é puro; só a escrita com `allow_writes` chega a ele (quem decide é o chamador).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz.candidates import Candidate, build_candidates, family_of
from harness_dast.domain.authz.compare import is_success_status
from harness_dast.domain.authz.config import AuthzConfig
from harness_dast.domain.authz.plan import Planned, skip_note, unique_exchanges
from harness_dast.domain.authz.result import AuthzNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord

_MAX_DESCRIPTION: Final = 1500
MAX_MASS_REQUESTS: Final = 400
"""Teto de pedidos de escrita da atribuição em massa por execução (um por candidato)."""


@dataclass(frozen=True)
class MassTask:
    """Enviar campos extras num `PUT`, `PATCH` ou `POST` provado pelo `probe`.

    Attributes:
        exchange: O pedido de escrita.
        read: Leitura para conferir o efeito (`GET` do mesmo modelo de caminho e conta; no
            `POST`, o `GET` irmão com o identificador do recurso criado), ou `None` (vale a
            própria resposta da escrita).
        candidates: Campos a testar, um por pedido, na ordem final.
        created: Se a operação cria recurso (`POST`): nada a restaurar e o recurso fica no alvo.
    """

    exchange: ExchangeRecord
    read: ExchangeRecord | None
    candidates: tuple[Candidate, ...] = ()
    created: bool = False
    candidate_readers: tuple[tuple[str, ExchangeRecord], ...] = ()


def is_json_object(text: str | None) -> bool:
    """O texto é um JSON válido cujo valor de topo é um objeto."""
    if text is None:
        return False
    try:
        return isinstance(json.loads(text), dict)
    except (ValueError, RecursionError):
        return False


def _segments(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def _is_marker(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def update_reader(item: ExchangeRecord, reads: Sequence[ExchangeRecord]) -> ExchangeRecord | None:
    """Escolhe GET provado, preferindo a conta escritora e o mesmo alvo concreto."""
    same_path = [r for r in reads if r.path == item.path]
    same = [r for r in same_path if r.account == item.account]
    exact = [r for r in same if r.target == item.target]
    other_exact = [r for r in same_path if r.target == item.target]
    chosen = exact or other_exact
    return chosen[0].model_copy(update={"account": item.account}) if chosen else None


def created_reader(item: ExchangeRecord, reads: Sequence[ExchangeRecord]) -> ExchangeRecord | None:
    """GET irmão provado, repetido com a conta que criou o recurso."""
    base = _segments(item.path)
    siblings = [
        read
        for read in reads
        if len(_segments(read.path)) == len(base) + 1
        and _segments(read.path)[:-1] == base
        and _is_marker(_segments(read.path)[-1])
    ]
    same = [read for read in siblings if read.account == item.account]
    chosen = same or siblings
    return chosen[0].model_copy(update={"account": item.account}) if chosen else None


def _echoes(operation: Operation | None) -> bool:
    """A operação declara um corpo de sucesso, onde o efeito pode aparecer sem leitor."""
    return operation is not None and any(
        response.body_schema is not None for response in operation.success_responses
    )


def _limited_note(item: ExchangeRecord, cut: int) -> AuthzNotTested:
    return skip_note(
        "mass_assignment",
        item,
        "candidates_limited",
        f"{cut} campo(s) derivado(s) do OpenAPI ficaram de fora do limite por operação "
        "(authz.max_derived_candidates; no POST, no máximo 4). Declare em "
        "authz.mass_assignment_fields os que importam.",
    )


def plan_mass_assignment(
    exchanges: Sequence[ExchangeRecord],
    public: frozenset[str],
    config: AuthzConfig,
    operations: Sequence[Operation] = (),
    infrastructure: frozenset[str] = frozenset(),
    budget: int = MAX_MASS_REQUESTS,
) -> Planned[MassTask]:
    """Atribuição em massa: cada `PUT`, `PATCH` ou `POST` com corpo JSON (objeto) do `probe`.

    Args:
        exchanges: Pedidos com sucesso do `probe`.
        public: Operações marcadas como públicas ou compartilhadas.
        config: Bloco `authz` do perfil (métodos, campos declarados e limites).
        operations: Operações do OpenAPI (fonte dos candidatos derivados).
        infrastructure: Caminhos que não são da API de negócio (login, saúde, preparação).
        budget: Teto de pedidos de escrita; a operação que o ultrapassa fica sem teste.

    Returns:
        As tarefas e o que ficou sem teste, com o motivo.
    """
    methods = frozenset(config.mass_assignment_methods)
    reads = [e for e in exchanges if e.method == "GET" and is_success_status(e.status)]
    by_id = {op.operation_id: op for op in operations}
    tasks: list[MassTask] = []
    skips: list[AuthzNotTested] = []
    planned = 0
    for item in unique_exchanges([e for e in exchanges if e.method in methods]):
        refusal = _refusal(item, public, infrastructure)
        if refusal is not None:
            skips.append(refusal)
            continue
        task, notes = _task(item, by_id.get(item.operation_id), operations, reads, config)
        skips.extend(notes)
        if task is None or not task.candidates:
            continue
        if planned + len(task.candidates) > budget:
            skips.append(
                skip_note(
                    "mass_assignment",
                    item,
                    "budget_exhausted",
                    f"O teto de {budget} pedidos de escrita por execução já estava planejado; "
                    "esta operação ficou sem teste.",
                )
            )
            continue
        planned += len(task.candidates)
        tasks.append(task)
    return Planned(tuple(tasks), tuple(skips))


def _refusal(
    item: ExchangeRecord, public: frozenset[str], infrastructure: frozenset[str]
) -> AuthzNotTested | None:
    """Anotação de por que o pedido não entra no plano, ou `None` se ele serve."""
    if item.operation_id in public:
        return skip_note("mass_assignment", item, "public_operation", "Marcada como pública.")
    if item.path in infrastructure:
        return skip_note(
            "mass_assignment",
            item,
            "infrastructure_path",
            "Caminho de login, saúde ou preparação: não é operação de negócio.",
        )
    if not is_json_object(item.body):
        return skip_note(
            "mass_assignment",
            item,
            "no_json_body",
            "O probe não guardou um corpo JSON (objeto) para esta operação.",
        )
    return None


def _task(
    item: ExchangeRecord,
    operation: Operation | None,
    operations: Sequence[Operation],
    reads: Sequence[ExchangeRecord],
    config: AuthzConfig,
) -> tuple[MassTask | None, list[AuthzNotTested]]:
    created = item.method == "POST"
    family = family_of(operation, operations) if operation is not None else ()
    candidates = build_candidates(operation, family, config, post=created)
    notes = [_limited_note(item, candidates.cut)] if candidates.cut else []
    if not created:
        return MassTask(item, update_reader(item, reads), candidates.candidates), notes
    reader = created_reader(item, reads)
    if reader is None and not _echoes(operation):
        notes.append(
            skip_note(
                "mass_assignment",
                item,
                "create_not_readable",
                "Não há GET provado do recurso criado (caminho com identificador) nem corpo de "
                "resposta declarado: o efeito não seria observável e o teste criaria recursos "
                "à toa.",
            )
        )
        return None, notes
    return MassTask(item, reader, candidates.candidates, created=True), notes


def count_candidates(tasks: Sequence[MassTask]) -> int:
    """Total de pares (operação, campo) planejados."""
    return sum(len(task.candidates) for task in tasks)


def describe_plan(tasks: Sequence[MassTask]) -> str:
    """Resumo legível do plano para o `--dry-run`: campos por operação, com a origem.

    Só nomes de operação e de campo; nunca valor. Limita o texto para não inundar o envelope.
    """
    parts: list[str] = []
    for task in tasks:
        names = ", ".join(
            item.name if item.source == "declared" else f"{item.name} ({item.source})"
            for item in task.candidates
        )
        parts.append(f"{task.exchange.method} {task.exchange.path}: {names}")
    text = "; ".join(parts)
    return text if len(text) <= _MAX_DESCRIPTION else text[: _MAX_DESCRIPTION - 3] + "..."
