"""Notas de `not_tested` do teste de autorização: escrita não autorizada e nada a repetir.

O teste entre contas roda por padrão no `run`, mas só LÊ: a atribuição em massa e os métodos de
escrita de `authz.vertical_methods` exigem `authz.allow_writes: true`, que vem da carta de
autorização. Sem isso, o que seria escrito não some em silêncio: vira `not_tested` com o motivo,
para que a ausência de achado nunca seja lida como "testado e seguro". Este módulo é puro e só
monta as notas; quem decide o plano é `application/authz/service.py`.
"""

from collections.abc import Sequence
from typing import Final

from harness_dast.domain.authz.config import CHECK_ORDER, AuthzCheck
from harness_dast.domain.authz.result import AuthzNotTested

WRITES_NOT_AUTHORIZED: Final = "writes_not_authorized"
NO_EXCHANGES: Final = "no_exchanges"
EXCHANGES_UNAVAILABLE: Final = "exchanges_unavailable"

MASS_BLOCKED_MESSAGE: Final = (
    "Escrita não autorizada pela carta: authz.allow_writes. A atribuição em massa escreve no "
    "alvo e não foi feita. Se a carta de autorização do dono do produto permite escrita, a "
    "pessoa registra isso na carta (attack.allow_authz_writes) e o perfil é gerado de novo."
)


def mass_blocked_note() -> AuthzNotTested:
    """Nota da atribuição em massa que não rodou por falta de `authz.allow_writes`."""
    return AuthzNotTested(
        check="mass_assignment",
        reason=WRITES_NOT_AUTHORIZED,
        message=MASS_BLOCKED_MESSAGE,
    )


def horizontal_write_blocked_note() -> AuthzNotTested:
    """Nota da escrita em recurso de outra conta que não rodou por falta de `allow_writes`."""
    return AuthzNotTested(
        check="horizontal_write",
        reason=WRITES_NOT_AUTHORIZED,
        message=(
            "Escrita não autorizada pela carta: authz.allow_writes. A escrita em recurso de "
            "outra conta (PUT e PATCH) altera o alvo e não foi feita; nenhum pedido foi enviado."
        ),
    )


def vertical_dropped_note(methods: Sequence[str]) -> AuthzNotTested:
    """Nota dos métodos de escrita retirados da verificação vertical.

    Args:
        methods: Métodos de escrita de `vertical_methods` que ficaram fora do plano.
    """
    names = ", ".join(methods)
    return AuthzNotTested(
        check="vertical",
        reason=WRITES_NOT_AUTHORIZED,
        message=(
            f"Escrita não autorizada pela carta: authz.allow_writes. Os métodos {names} de "
            "authz.vertical_methods foram retirados do plano; só GET e HEAD foram repetidos."
        ),
    )


def nothing_to_replay_notes(
    checks: Sequence[AuthzCheck], *, reason: str, why: str
) -> dict[AuthzCheck, AuthzNotTested]:
    """Uma nota por verificação quando não há pedido do `probe` para repetir.

    Args:
        checks: Verificações do plano.
        reason: Motivo estável (`no_exchanges` ou `exchanges_unavailable`).
        why: Explicação do motivo, em português.
    """
    return {
        check: AuthzNotTested(check=check, reason=reason, message=why)
        for check in CHECK_ORDER
        if check in checks
    }
