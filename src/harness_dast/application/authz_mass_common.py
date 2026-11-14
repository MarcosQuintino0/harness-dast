"""Peças comuns da atribuição em massa: corpo do `probe`, valor de teste e valor atual.

Usadas pelo fluxo de `PUT`/`PATCH` (`authz_checks_mass`) e pelo de `POST` (`authz_mass_post`).
Nada aqui envia pedido: só decide o que enviar e monta a anotação de "não testado".
"""

import json

from harness_dast.application.authz_sender import note
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz_candidates import Candidate, Injection
from harness_dast.domain.authz_config import normalize_field_name
from harness_dast.domain.authz_result import AuthzNotTested
from harness_dast.domain.authz_test_value import SKIP_ALREADY_THERE, pick_test_value
from harness_dast.domain.probe_exchange import ExchangeRecord


def as_object(text: str | None) -> dict[str, JsonValue] | None:
    """Corpo JSON do `probe` como objeto, ou `None` se ausente, malformado ou não objeto."""
    if text is None:
        return None
    try:
        parsed: JsonValue = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def already_sent(original: dict[str, JsonValue], injection: Injection) -> bool:
    """O corpo do probe já leva o campo com EXATAMENTE o valor de teste (mesmo tipo)."""
    if injection.name not in original:
        return False
    sent = original[injection.name]
    return type(sent) is type(injection.value) and sent == injection.value


def current_value(before: JsonValue | None, name: str) -> JsonValue:
    """Valor atual do campo na leitura anterior (primeiro nível, nome normalizado), ou `None`."""
    if not isinstance(before, dict):
        return None
    wanted = normalize_field_name(name)
    for key, value in before.items():
        if normalize_field_name(key) == wanted:
            return value
    return None


def no_body_note(exchange: ExchangeRecord) -> AuthzNotTested:
    """Anotação para operação sem corpo JSON (objeto) guardado pelo `probe`."""
    return note(
        "mass_assignment",
        exchange,
        "no_json_body",
        "O probe não guardou um corpo JSON (objeto) para esta operação.",
    )


def choose_injection(
    exchange: ExchangeRecord,
    original: dict[str, JsonValue],
    candidate: Candidate,
    current: JsonValue,
) -> Injection | AuthzNotTested:
    """Campo e valor a enviar, ou a anotação de por que o candidato não foi testado."""
    pick = pick_test_value(candidate, current)
    if pick.skip is not None:
        return note("mass_assignment", exchange, pick.skip, _skip_message(candidate, pick.skip))
    injection = Injection(candidate.name, pick.value)
    if already_sent(original, injection):
        return note(
            "mass_assignment",
            exchange,
            "same_value_in_body",
            f"O probe já enviou '{candidate.name}' com o valor de teste; não dá para "
            "distinguir. Fixe o campo do probe com uma regra em data-rules.yml ou "
            "declare outro valor em authz.mass_assignment_fields.",
        )
    return injection


def _skip_message(candidate: Candidate, reason: str) -> str:
    if reason == SKIP_ALREADY_THERE:
        return (
            f"O recurso já tem o valor de teste em '{candidate.name}'; não dá para distinguir "
            "o efeito. Declare o campo com outro valor em authz.mass_assignment_fields."
        )
    return (
        f"Não há valor de teste seguro para '{candidate.name}' (tipo, formato ou limites do "
        "OpenAPI). Declare o campo com um valor em authz.mass_assignment_fields se importa."
    )
