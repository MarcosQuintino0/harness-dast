"""Restauração do que o teste negativo gravou com `PUT` e `PATCH` (ADR 0051).

Depois de um caso que o servidor aceitou (2xx) ou respondeu com 5xx (estado incerto), o estágio
reenvia, com a mesma conta, o corpo VÁLIDO original do `exchanges.json` e espera 2xx. É o mesmo
princípio de `authz_restore.py`, sem releitura do recurso (limite declarado). Se uma parada
(janela, prazo, ZAP, alvo sem resposta) vier depois do envio, a restauração ainda é tentada pelo
mesmo caminho guardado (com a janela fechada nada sai); se não for confirmada, o aviso
`possible_unrestored_change` vai para `not_tested`. A parada nunca é engolida: quem chama a
levanta de novo. `POST` não tem restauração (não há valor anterior e `DELETE` é proibido). Nada
aqui decide veredito de segurança.
"""

from harness_dast.application.authz.sender import INTERRUPTIONS
from harness_dast.application.negative_sender import NegativeSender
from harness_dast.domain.authz.compare import is_success_status
from harness_dast.domain.mutation_snapshot import MutationSnapshot
from harness_dast.domain.negative_result import NegativeNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord

RESTORABLE_METHODS = frozenset({"PUT", "PATCH"})


def restore_original(
    sender: NegativeSender, exchange: ExchangeRecord, snapshot: MutationSnapshot | None = None
) -> bool:
    """Reenvia o pedido válido original; `True` só com 2xx.

    Raises:
        StopRun: O alvo ficou sem resposta em várias requisições seguidas.
        WindowClosed: Janela fechada.
        DeadlineReached: Prazo esgotado.
        ExternalToolError: Falha do proxy.
    """
    reply = sender.send(exchange, exchange.target, exchange.body, tag="restore:", snapshot=snapshot)
    return reply.problem is None and is_success_status(reply.status)


def try_restore(
    sender: NegativeSender, exchange: ExchangeRecord, snapshot: MutationSnapshot | None = None
) -> bool:
    """Como `restore_original`, mas devolve `False` se uma parada a impedir."""
    try:
        return restore_original(sender, exchange, snapshot)
    except INTERRUPTIONS:
        return False


def unrestored_note(exchange: ExchangeRecord, *, interrupted: bool) -> NegativeNotTested:
    """Aviso `possible_unrestored_change` para a conta e a operação."""
    why = (
        "a execução parou depois do envio e a restauração não pôde ser feita ou confirmada"
        if interrupted
        else "a restauração não foi confirmada"
    )
    return NegativeNotTested(
        operation_id=exchange.operation_id,
        method=exchange.method.upper(),
        path=exchange.path,
        reason="possible_unrestored_change",
        message=(
            f"Possível alteração não desfeita na conta '{exchange.account}', operação "
            f"'{exchange.operation_id}': um valor inválido foi enviado e {why}. "
            "Confira o estado e restaure por fora (reset do ambiente ou `hdast cleanup`)."
        ),
    )
