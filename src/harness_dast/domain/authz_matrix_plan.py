"""Plano e veredito da verificação `access_matrix` (ADR 0041). Módulo puro.

Para cada regra da tabela e cada papel em `deny`, o plano decide, SEM enviar nada, o que
acontece com a célula: um pedido a enviar, uma prova que o `probe` já gravou, ou "não testado"
com o motivo. O plano só ESCOLHE entre pedidos que o `probe` provou (`ExchangeRecord`): não
inventa caminho, não troca método e não adivinha identificador. O papel que a regra não cita é
`unspecified` e nunca é testado nem presumido proibido. O veredito e as células ficam em
`authz_matrix_cells`; as mensagens de "não testado", em `authz_matrix_notes`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz_matrix import AccessRule
from harness_dast.domain.authz_matrix_cells import MatrixTask, failed_by_probe_cell, not_tested_cell
from harness_dast.domain.authz_matrix_notes import (
    DELETE_NEVER,
    NO_ACCOUNT,
    NOT_REACHED,
    NOT_RUN,
    NOTHING_TO_DENY,
    WRITES_BLOCKED,
)
from harness_dast.domain.authz_matrix_report import MatrixCell, MatrixRow
from harness_dast.domain.authz_plan import Planned
from harness_dast.domain.authz_result import AuthzNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord

WRITE_METHODS: Final = frozenset({"POST", "PUT", "PATCH"})


@dataclass(frozen=True)
class MatrixPlan:
    """O plano da tabela.

    Attributes:
        roles: Papéis das colunas.
        rows: As linhas decididas no plano; a célula de um pedido a enviar vem como
            `not_tested` com o motivo `not_run` até o envio acontecer.
        sends: Células a decidir enviando um pedido.
        proved: Células que o `probe` já provou `failed` (nada a enviar).
        notes: Células proibidas que não dá para testar, e linhas sem nada a negar.
        candidates: Células `deny` (o que a verificação se propõe a testar).
    """

    roles: tuple[str, ...] = ()
    rows: tuple[MatrixRow, ...] = ()
    sends: tuple[MatrixTask, ...] = ()
    proved: tuple[MatrixTask, ...] = ()
    notes: tuple[AuthzNotTested, ...] = ()
    candidates: int = 0

    @property
    def planned(self) -> Planned[MatrixTask]:
        """Os pedidos a enviar e o que ficou sem teste, no formato dos demais planos."""
        return Planned(self.sends, self.notes)


def matrix_roles(role_order: Sequence[str], roles: Mapping[str, str]) -> tuple[str, ...]:
    """Papéis das colunas: `role_order` na ordem dela e depois os demais papéis das contas."""
    found: dict[str, None] = dict.fromkeys(role_order)
    found.update(dict.fromkeys(roles.values()))
    return tuple(found)


@dataclass
class _Row:
    """Linha em construção."""

    rule: AccessRule
    index: int
    exchanges: list[ExchangeRecord]
    cells: list[MatrixCell] = field(default_factory=list)


@dataclass(frozen=True)
class _Context:
    roles: Mapping[str, str]
    columns: tuple[str, ...]
    allow_writes: bool


@dataclass
class _Acc:
    sends: list[MatrixTask] = field(default_factory=list)
    proved: list[MatrixTask] = field(default_factory=list)
    notes: list[AuthzNotTested] = field(default_factory=list)
    candidates: int = 0


def plan_access_matrix(
    rules: Sequence[AccessRule],
    exchanges: Sequence[ExchangeRecord],
    roles: Mapping[str, str],
    role_order: Sequence[str],
    operations: Mapping[str, Operation],
    *,
    allow_writes: bool,
) -> MatrixPlan:
    """Decide, para cada célula da tabela, o que fazer (sem enviar nada).

    Args:
        rules: `authz.access_matrix`.
        exchanges: Pedidos com sucesso do `probe`.
        roles: Papel de cada conta (apelido -> papel), na ordem do perfil.
        role_order: `authz.role_order` (só ordena as colunas).
        operations: Operações do OpenAPI por `operationId` (dão método e caminho à linha que o
            `probe` não alcançou).
        allow_writes: `authz.allow_writes`.
    """
    columns = matrix_roles(role_order, roles)
    ctx = _Context(roles, columns, allow_writes)
    acc = _Acc()
    rows = tuple(
        _plan_row(
            _Row(rule, index, [e for e in exchanges if e.operation_id == rule.operation]),
            ctx,
            acc,
            operations.get(rule.operation),
        )
        for index, rule in enumerate(rules)
    )
    return MatrixPlan(
        roles=columns,
        rows=rows,
        sends=tuple(acc.sends),
        proved=tuple(acc.proved),
        notes=tuple(acc.notes),
        candidates=acc.candidates,
    )


def _plan_row(row: _Row, ctx: _Context, acc: _Acc, operation: Operation | None) -> MatrixRow:
    rule = row.rule
    first = row.exchanges[0] if row.exchanges else None
    if not rule.deny:
        acc.notes.append(_note(rule, operation, first, "nothing_to_deny", NOTHING_TO_DENY))
    for col, role in enumerate(ctx.columns):
        declared = rule.declared(role)
        if declared == "deny":
            acc.candidates += 1
            row.cells.append(_plan_denied(row, col, role, ctx, acc, operation))
        elif declared == "allow":
            proved = any(ctx.roles.get(e.account) == role for e in row.exchanges)
            row.cells.append(
                MatrixCell(
                    role=role,
                    declared="allow",
                    result="proved_allowed" if proved else "declared_allowed",
                )
            )
        else:
            row.cells.append(MatrixCell(role=role, declared="unspecified", result="unspecified"))
    method = first.method if first else (operation.method.upper() if operation else None)
    path = first.path if first else (operation.path if operation else None)
    return MatrixRow(operation_id=rule.operation, method=method, path=path, cells=tuple(row.cells))


def _plan_denied(
    row: _Row, col: int, role: str, ctx: _Context, acc: _Acc, operation: Operation | None
) -> MatrixCell:
    """Célula `deny`: prova do probe, pedido a enviar ou motivo de não testar."""
    rule = row.rule
    if not row.exchanges:
        return _skip(acc, rule, operation, None, role, ("not_reached_by_probe", NOT_REACHED))
    mine = next((e for e in row.exchanges if ctx.roles.get(e.account) == role), None)
    if mine is not None:
        task = MatrixTask(row.index, col, role, mine, mine.account, (mine.account, role))
        acc.proved.append(task)
        return failed_by_probe_cell(task)
    chosen = next(
        (e for e in row.exchanges if ctx.roles.get(e.account) in rule.allow), row.exchanges[0]
    )
    reason = _blocked_reason(chosen.method, allow_writes=ctx.allow_writes)
    if reason is not None:
        return _skip(acc, rule, operation, chosen, role, reason)
    actor = next((alias for alias, r in ctx.roles.items() if r == role), None)
    if actor is None:
        return _skip(acc, rule, operation, chosen, role, ("no_account_for_role", NO_ACCOUNT))
    owner = (chosen.account, ctx.roles.get(chosen.account))
    acc.sends.append(MatrixTask(row.index, col, role, chosen, actor, owner))
    return not_tested_cell(role, "not_run", NOT_RUN)


def _blocked_reason(method: str, *, allow_writes: bool) -> tuple[str, str] | None:
    """Motivo (estável e mensagem) de o método não poder ser enviado, ou `None` se pode."""
    if method == "DELETE":
        return "delete_never_tested", DELETE_NEVER
    if method in WRITE_METHODS and not allow_writes:
        return "writes_not_allowed", WRITES_BLOCKED
    return None


def _skip(
    acc: _Acc,
    rule: AccessRule,
    operation: Operation | None,
    exchange: ExchangeRecord | None,
    role: str,
    why: tuple[str, str],
) -> MatrixCell:
    acc.notes.append(_note(rule, operation, exchange, why[0], f"Papel {role}: {why[1]}"))
    return not_tested_cell(role, why[0], why[1])


def _note(
    rule: AccessRule,
    operation: Operation | None,
    exchange: ExchangeRecord | None,
    reason: str,
    message: str,
) -> AuthzNotTested:
    return AuthzNotTested(
        check="access_matrix",
        operation_id=rule.operation,
        method=exchange.method if exchange else (operation.method.upper() if operation else None),
        path=exchange.path if exchange else (operation.path if operation else None),
        reason=reason,
        message=message,
    )


def assemble_rows(
    plan: MatrixPlan, resolved: Mapping[tuple[int, int], MatrixCell]
) -> tuple[MatrixRow, ...]:
    """As linhas do plano com as células já decididas no envio no lugar do `not_run`."""
    return tuple(
        row.model_copy(
            update={"cells": tuple(resolved.get((r, c), cell) for c, cell in enumerate(row.cells))}
        )
        for r, row in enumerate(plan.rows)
    )
