"""Células e veredito da verificação `access_matrix` (ADR 0041). Módulo puro.

Cada célula `deny` vira um pedido a enviar (`MatrixTask`) ou já nasce decidida. O veredito é a
regra da verificação vertical: só 401 e 403 provam a negação; `2xx` é falha; o resto é "não
testado", nunca "seguro".
"""

from dataclasses import dataclass
from typing import Final, Literal

from harness_dast.domain.authz_matrix_report import MatrixCell
from harness_dast.domain.probe_exchange import ExchangeRecord

DENIED_STATUSES: Final = frozenset({401, 403})
"""Só 401 e 403 provam que o servidor negou; 400, 404, 409 e 422 são ambíguos."""
_SUCCESS_FIRST: Final = 200
_SUCCESS_LAST: Final = 299

Verdict = Literal["passed", "failed", "inconclusive"]


@dataclass(frozen=True)
class MatrixTask:
    """Uma célula `deny` a decidir enviando um pedido, ou já provada pelo `probe`.

    Attributes:
        row: Posição da linha na tabela.
        col: Posição do papel em `MatrixPlan.roles`.
        role: Papel proibido.
        exchange: Pedido provado pelo `probe` (o repetido, ou o que já provou a contradição).
        actor: Apelido da conta que envia (a primeira do papel); na prova do `probe`, a conta
            que o `probe` usou.
        owner: Apelido e papel da conta que enviou `exchange` no `probe`.
    """

    row: int
    col: int
    role: str
    exchange: ExchangeRecord
    actor: str
    owner: tuple[str, str | None]


def judge_matrix_cell(status: int | None) -> Verdict:
    """401 e 403 = `passed`; qualquer `2xx` = `failed`; o resto (ou sem resposta) é inconclusivo."""
    if status in DENIED_STATUSES:
        return "passed"
    if status is not None and _SUCCESS_FIRST <= status <= _SUCCESS_LAST:
        return "failed"
    return "inconclusive"


def not_tested_cell(role: str, reason: str, message: str) -> MatrixCell:
    """Célula proibida que não pôde ser testada."""
    return MatrixCell(
        role=role, declared="deny", result="not_tested", reason=reason, message=message
    )


def failed_by_probe_cell(task: MatrixTask) -> MatrixCell:
    """Célula que o `probe` já provou: a conta do papel proibido obteve `2xx` com ele."""
    return MatrixCell(
        role=task.role,
        declared="deny",
        result="failed",
        status=task.exchange.status,
        account=task.exchange.account,
        source="probe",
    )


def cell_from_reply(task: MatrixTask, status: int | None) -> MatrixCell:
    """Célula decidida pela resposta do pedido enviado (veja `judge_matrix_cell`)."""
    verdict = judge_matrix_cell(status)
    if verdict == "inconclusive":
        shown = "sem resposta" if status is None else f"status {status}"
        return not_tested_cell(
            task.role,
            "inconclusive",
            f"Resposta sem conclusão ({shown}); não conta como seguro. Só 401 e 403 provam "
            "a negação.",
        ).model_copy(update={"status": status, "account": task.actor, "source": "replay"})
    return MatrixCell(
        role=task.role,
        declared="deny",
        result=verdict,
        status=status,
        account=task.actor,
        source="replay",
    )
