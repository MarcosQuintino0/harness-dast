"""Laço do teste negativo: envia os casos do plano e classifica a reação (ADR 0051).

Para cada caso, na ordem do plano: confere o orçamento (`max_requests` conta casos e
restaurações), envia pelo `NegativeSender` (escopo, `deny_paths`, taxa, janela, prazo, trava e
auditoria), pede o veredito ao domínio (`negative_verdict`) e, se o servidor aceitou ou falhou
com 5xx, monta o achado e restaura (`PUT`/`PATCH`) ou conta o recurso criado (`POST`). Uma
operação é encerrada (os casos seguintes dela não saem) quando o escopo ou a conta recusa, a
conta perde a permissão, o recurso some, uma restauração não se confirma ou um `POST` já criou
`MAX_CREATED_PER_OPERATION` recursos. Paradas (janela, prazo, ZAP, alvo sem resposta) interrompem
o laço e voltam como `NegativeOutcome`; nunca são engolidas. Nenhum valor enviado nem corpo de
resposta é guardado: só o veredito, os códigos e os NOMES de campo.
"""

from dataclasses import dataclass
from typing import Final

from harness_dast.application.authz_sender import INTERRUPTIONS, Reply, StopRun
from harness_dast.application.negative_restore import (
    RESTORABLE_METHODS,
    restore_original,
    try_restore,
    unrestored_note,
)
from harness_dast.application.negative_sender import NegativeSender
from harness_dast.application.run_support import DeadlineReached, WindowClosed
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.negative_findings import build_negative_finding
from harness_dast.domain.negative_plan import NegativeCase, NegativePlan
from harness_dast.domain.negative_request import render_case
from harness_dast.domain.negative_result import (
    ClassSummary,
    NegativeFinding,
    NegativeNotTested,
    NegativeTechnique,
    OperationSummary,
)
from harness_dast.domain.negative_tally import NegativeTally
from harness_dast.domain.negative_verdict import STOP_REASONS, judge, reason_text
from harness_dast.domain.probe_result import ProbeStatus

MAX_CREATED_PER_OPERATION: Final = 2
"""`POST` aceito mais vezes que isto na mesma operação encerra os casos dela."""

_OperationKey = tuple[str, str, str]


@dataclass(frozen=True)
class NegativeOutcome:
    """Resultado do laço.

    Attributes:
        status: `completed` ou o motivo da parada antecipada.
        stop_message: Explicação da parada.
        requests_sent: Requisições enviadas (casos e restaurações).
        accounts: Contas que enviaram.
        created_resources: Recursos que um `POST` aceito pode ter criado.
        restored_resources: `PUT` e `PATCH` restaurados com sucesso.
        by_class: Totais por classe.
        operations: Totais por operação.
        findings: Achados.
        not_tested: O que não foi testado e por quê.
    """

    status: ProbeStatus
    stop_message: str | None
    requests_sent: int
    accounts: tuple[str, ...]
    created_resources: int
    restored_resources: int
    by_class: tuple[ClassSummary, ...]
    operations: tuple[OperationSummary, ...]
    findings: tuple[NegativeFinding, ...]
    not_tested: tuple[NegativeNotTested, ...]


def need_restore(method: str) -> int:
    """Requisições que ficam reservadas para restaurar (1 em `PUT` e `PATCH`, senão 0)."""
    return 1 if method.upper() in RESTORABLE_METHODS else 0


def _stop_status(error: Exception) -> tuple[ProbeStatus, str]:
    if isinstance(error, StopRun):
        return error.status, error.message
    if isinstance(error, WindowClosed):
        return "stopped_window", error.message
    if isinstance(error, DeadlineReached):
        return "stopped_deadline", error.message
    message = error.message if isinstance(error, ExternalToolError) else str(error)
    return "stopped_zap", message


class NegativeRunner:
    """Executa os casos do plano (veja o docstring do módulo)."""

    def __init__(self, sender: NegativeSender, *, product: str, max_requests: int) -> None:
        """Cria o executor.

        Args:
            sender: Emissor protegido (escopo, taxa, janela, prazo, trava, auditoria).
            product: Produto (entra no fingerprint dos achados).
            max_requests: Teto de envios do estágio.
        """
        self._sender = sender
        self._product = product
        self._max = max_requests
        self._tally = NegativeTally(())
        self._findings: list[NegativeFinding] = []
        self._notes: list[NegativeNotTested] = []
        self._closed: dict[_OperationKey, str] = {}
        self._left: dict[tuple[_OperationKey, str], int] = {}
        self._created = 0
        self._created_by_op: dict[_OperationKey, int] = {}
        self._restored = 0

    def run(self, plan: NegativePlan) -> NegativeOutcome:
        """Envia os casos na ordem do plano.

        Returns:
            O resultado; janela fechada e prazo esgotado voltam como `stopped_window` e
            `stopped_deadline`, falha do proxy como `stopped_zap` e alvo sem resposta em
            sequência como `stopped_target_unresponsive`.
        """
        self._tally = NegativeTally(plan.cases)
        status: ProbeStatus = "completed"
        message: str | None = None
        done = 0
        try:
            for case in plan.cases:
                self._case(case)
                done += 1
        except INTERRUPTIONS as error:
            status, message = _stop_status(error)
            self._notes.append(_stopped_note(len(plan.cases) - done - 1))
        return NegativeOutcome(
            status=status,
            stop_message=message,
            requests_sent=self._sender.sent,
            accounts=self._sender.accounts,
            created_resources=self._created,
            restored_resources=self._restored,
            by_class=self._tally.by_class(),
            operations=self._tally.operations(),
            findings=tuple(self._findings),
            not_tested=(*plan.not_tested, *self._notes, *self._left_notes()),
        )

    def _case(self, case: NegativeCase) -> None:
        key = case.key
        if key in self._closed:
            self._skip(key, self._closed[key])
            return
        need = 1 + need_restore(case.exchange.method)
        if self._sender.sent + need > self._max:
            self._skip(key, "budget")
            return
        reply = self._send(case)
        if reply.problem is not None:
            self._problem(case, reply)
            return
        reaction = judge(reply.status, case.exchange.method)
        self._tally.record(case, reaction.verdict)
        if reaction.verdict in {"accepted", "server_error"}:
            technique: NegativeTechnique = (
                "input_accepted" if reaction.verdict == "accepted" else "input_server_error"
            )
            self._failure(case, technique, reply.status or 0)
        elif reaction.verdict == "inconclusive":
            self._inconclusive(case, reaction.reason or "inconclusive", reply)

    def _skip(self, key: _OperationKey, reason: str) -> None:
        self._left[(key, reason)] = self._left.get((key, reason), 0) + 1

    def _send(self, case: NegativeCase) -> Reply:
        """Envia o caso; se uma parada vier de um PUT ou PATCH, tenta desfazer antes de seguir."""
        target, body = render_case(case)
        try:
            reserve = need_restore(case.exchange.method)
            return self._sender.send(case.exchange, target, body, reserve=reserve)
        except (StopRun, ExternalToolError):
            # Janela e prazo são conferidos ANTES do envio (nada saiu); aqui a escrita pode ter
            # chegado ao alvo, então a restauração é tentada e, sem confirmação, avisada.
            if case.exchange.method.upper() in RESTORABLE_METHODS and not try_restore(
                self._sender, case.exchange
            ):
                self._notes.append(unrestored_note(case.exchange, interrupted=True))
            raise

    def _problem(self, case: NegativeCase, reply: Reply) -> None:
        key = case.key
        if reply.problem == "scope":
            reason = "scope_denied"
            message = (
                "O escopo do perfil recusou o pedido (caminho negado ou método fora do escopo); "
                "nada foi enviado."
            )
        else:
            reason = "account_unavailable"
            message = "A conta do pedido não conseguiu abrir sessão (login recusado)."
        self._closed[key] = reason
        self._notes.append(_case_note(case, reason, message))

    def _inconclusive(self, case: NegativeCase, reason: str, reply: Reply) -> None:
        message = (
            f"Sem conclusão: {reason_text(reason)} (status {reply.status}); não conta como seguro."
        )
        self._notes.append(_case_note(case, reason, message))
        if reason in STOP_REASONS:
            self._closed[case.key] = reason

    def _failure(self, case: NegativeCase, technique: NegativeTechnique, status: int) -> None:
        """Aceitou ou 5xx: restaura (PUT, PATCH) ou conta o criado (POST) e monta o achado."""
        exchange = case.exchange
        method = exchange.method.upper()
        restored: bool | None = None
        stopped: Exception | None = None
        created = method == "POST"
        if method in RESTORABLE_METHODS:
            restored, stopped = self._restore(case)
        if created:
            self._count_created(case)
        self._findings.append(
            build_negative_finding(
                product=self._product,
                technique=technique,
                case=case,
                status=status,
                restored=restored,
                created=created,
            )
        )
        if stopped is not None:
            raise stopped

    def _restore(self, case: NegativeCase) -> tuple[bool, Exception | None]:
        exchange = case.exchange
        try:
            ok = restore_original(self._sender, exchange)
        except INTERRUPTIONS as stop:
            self._notes.append(unrestored_note(exchange, interrupted=True))
            self._closed[case.key] = "restore_pending"
            return False, stop
        if ok:
            self._restored += 1
            return True, None
        self._notes.append(unrestored_note(exchange, interrupted=False))
        self._closed[case.key] = "restore_pending"
        return False, None

    def _count_created(self, case: NegativeCase) -> None:
        key = case.key
        self._created += 1
        self._created_by_op[key] = self._created_by_op.get(key, 0) + 1
        if self._created_by_op[key] >= MAX_CREATED_PER_OPERATION:
            self._closed[key] = "created_limit"

    def _left_notes(self) -> list[NegativeNotTested]:
        notes: list[NegativeNotTested] = []
        for (key, reason), count in self._left.items():
            operation_id, method, path = key
            notes.append(
                NegativeNotTested(
                    operation_id=operation_id,
                    method=method,
                    path=path,
                    reason=reason,
                    message=_left_message(reason, count),
                )
            )
        return notes


def _left_message(reason: str, count: int) -> str:
    if reason == "budget":
        return f"{count} caso(s) não foram enviados: o orçamento (negative.max_requests) acabou."
    if reason == "created_limit":
        return (
            f"{count} caso(s) não foram enviados: um POST já criou "
            f"{MAX_CREATED_PER_OPERATION} recurso(s) com valor inválido; não se enche o ambiente "
            "de lixo (limpe com `hdast cleanup` ou o reset do ambiente)."
        )
    if reason == "restore_pending":
        return (
            f"{count} caso(s) não foram enviados: a operação tem uma restauração pendente "
            "(veja possible_unrestored_change)."
        )
    return f"{count} caso(s) não foram enviados: a operação foi encerrada ({reason_text(reason)})."


def _case_note(case: NegativeCase, reason: str, message: str) -> NegativeNotTested:
    return NegativeNotTested(
        operation_id=case.exchange.operation_id,
        method=case.exchange.method.upper(),
        path=case.exchange.path,
        reason=reason,
        message=message,
        field=case.field,
        case_class=case.case_class,
    )


def _stopped_note(remaining: int) -> NegativeNotTested:
    return NegativeNotTested(
        reason="stopped",
        message=f"A execução parou antes de {max(remaining, 0)} caso(s) do plano.",
    )
