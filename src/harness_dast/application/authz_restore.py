"""Restauração do que as verificações de escrita alteraram (atribuição em massa e outra conta).

As duas verificações que escrevem no alvo (`mass_assignment` e `horizontal_write`) seguem a mesma
regra: quem restaura é a conta dona do pedido provado (`exchange.account`), que reenvia o mesmo
`PUT` ou `PATCH` com o valor anterior de UM campo e relê o recurso para conferir. Se uma parada
(janela, prazo, ZAP, alvo sem resposta) vier depois do envio, a restauração ainda é tentada pelo
mesmo caminho guardado (com a janela fechada nada sai); se não houver como confirmá-la, o aviso
`possible_unrestored_change` vai para `not_tested`. A parada nunca é engolida: quem chama a levanta
de novo. Nada aqui decide veredito de segurança.
"""

from dataclasses import dataclass

from harness_dast.application.authz_sender import (
    INTERRUPTIONS,
    CheckContext,
    CheckResult,
    note,
)
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz_compare import holds_value, is_success_status, parse_json
from harness_dast.domain.authz_config import AuthzCheck
from harness_dast.domain.authz_result import AuthzNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord


@dataclass
class Pending:
    """Estado de uma escrita que ainda pode ter deixado alteração no alvo.

    Attributes:
        attempted: A escrita foi enviada e a restauração ainda não foi concluída.
        known: `previous` já foi confirmado pela leitura posterior.
        previous: Valor anterior do campo, para a restauração.
    """

    attempted: bool = False
    known: bool = False
    previous: JsonValue = None


def read_body(ctx: CheckContext, read: ExchangeRecord | None) -> JsonValue | None:
    """Corpo JSON da leitura (um `GET` provado, pela conta dele), ou `None` se falhou."""
    if read is None:
        return None
    reply = ctx.sender.send(read, read.account)
    return parse_json(reply.body) if is_success_status(reply.status) else None


def is_restorable(previous: JsonValue) -> bool:
    """Só valor escalar existente pode ser devolvido."""
    return previous is not None and not isinstance(previous, dict | list)


def restore(
    ctx: CheckContext,
    exchange: ExchangeRecord,
    read: ExchangeRecord | None,
    original: dict[str, JsonValue],
    field: tuple[str, JsonValue],
    changed: tuple[str, ...],
    previous: JsonValue,
) -> bool | None:
    """Devolve o valor anterior e confere pela leitura; `None` se não havia valor a devolver.

    Args:
        ctx: Contexto da verificação.
        exchange: O pedido de escrita provado (reenviado pela conta dona).
        read: Leitura que confirma o efeito (pode ser `None`: então não confirma).
        original: Corpo que o `probe` enviou.
        field: Nome do campo e valor de teste que foi escrito.
        changed: Caminhos em que o valor de teste apareceu.
        previous: Valor anterior do campo.
    """
    if not is_restorable(previous):
        return None
    ctx.sender.send(
        exchange, exchange.account, body={**original, field[0]: previous}, with_body=True
    )
    again = read_body(ctx, read)
    return again is not None and not holds_value(again, changed, field[1])


def try_restore(
    ctx: CheckContext,
    exchange: ExchangeRecord,
    original: dict[str, JsonValue],
    field_name: str,
    previous: JsonValue,
) -> bool:
    """Tenta devolver o valor anterior depois de uma parada; `False` se não deu para confirmar."""
    if not is_restorable(previous):
        return False
    try:
        reply = ctx.sender.send(
            exchange, exchange.account, body={**original, field_name: previous}, with_body=True
        )
    except INTERRUPTIONS:
        return False
    return reply.problem is None and is_success_status(reply.status)


def unrestored_note(
    check: AuthzCheck, exchange: ExchangeRecord, what: str, after: str, cause: str
) -> AuthzNotTested:
    """Aviso `possible_unrestored_change`.

    Args:
        check: Verificação que escreveu.
        exchange: Pedido de escrita (a conta dona é `exchange.account`).
        what: O que foi feito, por exemplo "o campo extra 'x' foi enviado".
        after: Depois de quê a execução pode ter parado, por exemplo "do PUT".
        cause: `interrupted` (a execução parou) ou outro valor (restauração não confirmada).
    """
    why = (
        f"a execução parou depois {after} e a restauração não pôde ser feita ou confirmada"
        if cause == "interrupted"
        else "a restauração não foi confirmada"
    )
    return note(
        check,
        exchange,
        "possible_unrestored_change",
        f"Possível alteração não desfeita na conta '{exchange.account}', operação "
        f"'{exchange.operation_id}': {what} e {why}. "
        "Confira o estado da conta e restaure por fora (reset do ambiente ou `cleanup`).",
    )


def after_interruption(
    ctx: CheckContext,
    out: CheckResult,
    pending: Pending,
    attempt: tuple[AuthzCheck, ExchangeRecord, dict[str, JsonValue]],
    field_name: str,
    fallback: JsonValue,
    wording: tuple[str, str],
) -> None:
    """Parada depois da escrita: tenta desfazer; se não der, avisa em `not_tested`.

    A restauração passa pelo mesmo caminho guardado: com a janela fechada, o prazo vencido
    ou a trava acionada nada é enviado e só o aviso fica registrado.

    Args:
        ctx: Contexto da verificação.
        out: Resultado em andamento (recebe o aviso).
        pending: Estado da escrita.
        attempt: Verificação, pedido de escrita provado e corpo do `probe`.
        field_name: Campo escrito.
        fallback: Valor anterior da leitura inicial, se `pending` ainda não o confirmou.
        wording: (o que foi feito, depois de quê) para a mensagem.
    """
    if not pending.attempted:
        return
    check, exchange, original = attempt
    previous = pending.previous if pending.known else fallback
    if not try_restore(ctx, exchange, original, field_name, previous):
        out.not_tested.append(
            unrestored_note(check, exchange, wording[0], wording[1], "interrupted")
        )
