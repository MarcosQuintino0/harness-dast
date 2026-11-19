"""Padrões do pedido mínimo para autorização, limites, login e ataque (ADR 0120).

Cada função devolve a seção da carta com a resposta explícita da pessoa ou, sem ela, o padrão da
tabela de `request_defaults`, e registra em `applied` o que a CLI aplicou. As três escritas
(`authz`, valores inválidos e upload) nunca têm padrão: só a pergunta 4 `true` ou a chave
individual explícita as liga. Este módulo é puro.
"""

from datetime import date, timedelta
from typing import Final

from harness_dast.domain.letter import (
    Answer,
    AttackSection,
    AuthorizationSection,
    AuthSection,
    Letter,
    LimitsSection,
)
from harness_dast.domain.letter_collect import Collector
from harness_dast.domain.request_answers import (
    PERSON_QUOTE,
    default_answer,
    endorse,
    explicit,
    flag,
    pick,
    text,
)
from harness_dast.domain.request_defaults import (
    FULL_WINDOW,
    VALIDITY_DAYS,
    RequestDefault,
)

_MAX_REFERENCE: Final = 200
_FLAG_FIELDS: Final = (
    ("inject_headers", "scan.inject_headers"),
    ("oast", "scan.oast"),
    ("allow_rate_tests", "extra_checks.allow_rate_tests"),
    ("experimental_rules", "extra_checks.experimental_rules"),
    ("inventory", "extra_checks.inventory"),
)
_WRITE_KEYS: Final = ("allow_authz_writes", "allow_invalid_input_writes", "allow_upload_scan")


def fill_authorization(
    letter: Letter, today: date, timezone: str, applied: list[RequestDefault]
) -> AuthorizationSection:
    """Referência (com o dono), validade e janela, se a pessoa não as respondeu."""
    section = letter.authorization
    reference = explicit(section.reference)
    if reference is None:
        default = RequestDefault(
            field="authorization.reference",
            value=_reference(letter, today),
            reason="o pedido mínimo não traz documento de autorização; a referência registra "
            "o dono que a pessoa informou",
        )
        applied.append(default)
        reference = default_answer(default.value)
    valid_until = explicit(section.valid_until)
    if valid_until is None:
        default = RequestDefault(
            field="authorization.valid_until",
            value=today + timedelta(days=VALIDITY_DAYS),
            reason=f"{VALIDITY_DAYS} dias a partir do cadastro; passado o prazo, é preciso "
            "cadastrar de novo",
        )
        applied.append(default)
        valid_until = default_answer(default.value)
    windows = explicit(section.windows)
    if windows is None:
        default = RequestDefault(
            field="authorization.windows",
            value=f"{FULL_WINDOW} {timezone}",
            reason="todos os dias, o dia inteiro, no fuso da máquina; o ambiente é de teste",
        )
        applied.append(default)
        windows = default_answer([default.value])
    return section.model_copy(
        update={"reference": reference, "valid_until": valid_until, "windows": windows}
    )


def _reference(letter: Letter, today: date) -> str:
    head = f"pedido-{letter.product}-{today.isoformat()} (dono: "
    owner = " ".join((text(letter.gates.product_owner) or "").replace("|", " ").split())
    room = max(0, _MAX_REFERENCE - len(head) - 1)
    return f"{head}{owner[:room]})"


def fill_limits(letter: Letter, applied: list[RequestDefault]) -> LimitsSection:
    """Os três limites de carga, com o padrão onde a pessoa não respondeu."""
    limits = letter.limits
    return limits.model_copy(
        update={
            "requests_per_second": pick(
                limits.requests_per_second, "limits.requests_per_second", applied
            ),
            "max_duration_minutes": pick(
                limits.max_duration_minutes, "limits.max_duration_minutes", applied
            ),
            "zap_threads_per_host": pick(
                limits.zap_threads_per_host, "limits.zap_threads_per_host", applied
            ),
        }
    )


def fill_auth(letter: Letter, applied: list[RequestDefault]) -> AuthSection:
    """Logins por minuto padrão; só para `login_password` (a chave de API não tem login)."""
    auth = letter.auth
    if text(auth.type) != "login_password":
        return auth
    limit = pick(auth.login_max_per_minute, "auth.login_max_per_minute", applied)
    return auth.model_copy(update={"login_max_per_minute": limit})


def fill_attack(
    attack: AttackSection, c: Collector, applied: list[RequestDefault]
) -> AttackSection:
    """Força, classes de resposta, ritmo e as cinco capacidades; as escritas só pela pergunta 4."""
    update: dict[str, Answer | None] = {
        "strength": pick(attack.strength, "scan.strength", applied),
        "include_outcomes": pick(attack.include_outcomes, "scan.include_outcomes", applied),
        "pacing": pick(attack.pacing, "scan.pacing", applied),
    }
    for name, field in _FLAG_FIELDS:
        update[name] = endorse(pick(getattr(attack, name), field, applied))
    update.update(_fill_writes(attack, c))
    return attack.model_copy(update=update)


def _fill_writes(attack: AttackSection, c: Collector) -> dict[str, Answer | None]:
    """Pergunta 4: liga as três escritas só com `true`; a chave individual explícita vence."""
    group = flag(c, "attack.allow_data_writes", attack.allow_data_writes)
    update: dict[str, Answer | None] = {}
    for name in _WRITE_KEYS:
        own = explicit(getattr(attack, name))
        if own is not None:
            update[name] = endorse(own)
        elif group:
            update[name] = default_answer(True, PERSON_QUOTE)
    return update
