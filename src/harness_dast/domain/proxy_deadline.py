"""Prazo da política do proxy de escopo: até quando a execução pode enviar requisições.

O proxy nega tudo depois de `not_after`. O prazo nunca é maior que o menor entre: a duração
máxima do perfil, o fim do último dia de validade da autorização e o primeiro minuto em que
nenhuma janela de execução está aberta. Este módulo é puro.
"""

from datetime import UTC, datetime, timedelta

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.window import ensure_aware

_ONE_MINUTE = timedelta(minutes=1)


def compute_policy_deadline(profile: ProductProfile, now: datetime) -> datetime:
    """Calcula o `not_after` da política de uma execução iniciada em `now`.

    Args:
        profile: Perfil do produto.
        now: Instante de início, com fuso. Autorização e janela devem estar válidas nele
            (o chamador confere antes com `profile.ensure_runnable`).

    Returns:
        Instante em UTC, no máximo `now + limits.max_duration_minutes`, nunca depois do fim
        do dia de `scope.authorization.valid_until` (UTC) e nunca depois de a janela fechar.

    Raises:
        ConfigError: Se `now` não tiver fuso.
    """
    ensure_aware(now)
    start = now.astimezone(UTC)
    by_duration = start + timedelta(minutes=profile.limits.max_duration_minutes)
    valid_until = profile.scope.authorization.valid_until
    by_authorization = datetime(
        valid_until.year, valid_until.month, valid_until.day, tzinfo=UTC
    ) + timedelta(days=1)
    limit = min(by_duration, by_authorization)
    cursor = start.replace(second=0, microsecond=0) + _ONE_MINUTE
    while cursor < limit:
        if not any(window.is_open(cursor) for window in profile.scope.windows):
            return cursor
        cursor += _ONE_MINUTE
    return limit
