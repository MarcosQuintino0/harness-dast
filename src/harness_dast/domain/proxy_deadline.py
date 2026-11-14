"""Prazo da política do proxy de escopo: até quando a execução pode enviar requisições.

O proxy nega tudo depois de `not_after`, que é a VALIDADE DA PILHA, não o prazo de uma
varredura. Cada execução (`run`, `probe`, `scan`) tem o seu prazo, contado do início dela e
limitado por `limits.max_duration_minutes` (isso vive na CLI: `RunGate`, `scan`). A pilha dura
o tempo de uma execução mais uma folga (`STACK_MARGIN_MINUTES`) para o ajuste do `probe` antes do
`run`, e nunca passa do fim do último dia de validade da autorização nem do primeiro minuto em
que nenhuma janela de execução está aberta. Este módulo é puro.
"""

from datetime import UTC, datetime, timedelta

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.window import ensure_aware

_ONE_MINUTE = timedelta(minutes=1)

STACK_MARGIN_MINUTES = 60
"""Folga da pilha sobre `max_duration_minutes`: tempo para ajustar o `probe` antes do `run`."""


def stack_validity_minutes(profile: ProductProfile) -> int:
    """Quanto a pilha vale a partir da subida, antes do corte por autorização e janela."""
    return profile.limits.max_duration_minutes + STACK_MARGIN_MINUTES


def compute_policy_deadline(profile: ProductProfile, now: datetime) -> datetime:
    """Calcula o `not_after` da política (validade da pilha) de uma pilha subida em `now`.

    Args:
        profile: Perfil do produto.
        now: Instante de início, com fuso. Autorização e janela devem estar válidas nele
            (o chamador confere antes com `profile.ensure_runnable`).

    Returns:
        Instante em UTC, no máximo `now + stack_validity_minutes(profile)`, nunca depois do fim
        do dia de `scope.authorization.valid_until` (UTC) e nunca depois de a janela fechar.
        O prazo de cada execução é outro: conta do início dela e não passa de
        `limits.max_duration_minutes`.

    Raises:
        ConfigError: Se `now` não tiver fuso.
    """
    ensure_aware(now)
    start = now.astimezone(UTC)
    by_validity = start + timedelta(minutes=stack_validity_minutes(profile))
    valid_until = profile.scope.authorization.valid_until
    by_authorization = datetime(
        valid_until.year, valid_until.month, valid_until.day, tzinfo=UTC
    ) + timedelta(days=1)
    limit = min(by_validity, by_authorization)
    cursor = start.replace(second=0, microsecond=0) + _ONE_MINUTE
    while cursor < limit:
        if not any(window.is_open(cursor) for window in profile.scope.windows):
            return cursor
        cursor += _ONE_MINUTE
    return limit
