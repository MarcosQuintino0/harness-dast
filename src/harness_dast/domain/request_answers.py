"""Respostas da carta `kind: request`: ler a explícita ou aplicar o padrão (ADR 0120).

Auxiliares de `request_letter` e `request_fill`. Os valores padrão entram na carta como resposta
`carta` com uma frase que diz de onde vêm (`DEFAULT_QUOTE`), para os leitores existentes os
aceitarem sem mudança. Este módulo é puro.
"""

from typing import Final

from harness_dast.domain.letter import Answer
from harness_dast.domain.letter_collect import INVALID_VALUE, Collector
from harness_dast.domain.request_defaults import REQUEST_DEFAULTS, RequestDefault

DEFAULT_QUOTE: Final = "Padrão do pedido mínimo (ADR 0120), aplicado pela CLI."
PERSON_QUOTE: Final = "Resposta da pessoa no pedido mínimo (ADR 0120)."
_BOOL_TEXT: Final = "Responda true (sim) ou false (não)."


def explicit(answer: Answer | None) -> Answer | None:
    """A resposta, se é explícita: origem `carta` ou `pessoa`, com valor."""
    if answer is None or answer.source == "desconhecido" or answer.value is None:
        return None
    return answer


def text(answer: Answer | None) -> str | None:
    """O texto não vazio de uma resposta explícita, ou `None`."""
    given = explicit(answer)
    if given is None or not isinstance(given.value, str) or not given.value.strip():
        return None
    return given.value.strip()


def default_answer(value: object, quote: str = DEFAULT_QUOTE) -> Answer:
    """Resposta montada pela CLI, com a frase que diz de onde veio."""
    return Answer(value=value, source="carta", quote=quote)


def pick(answer: Answer | None, field: str, applied: list[RequestDefault]) -> Answer:
    """A resposta explícita ou, sem ela, o padrão da tabela (registrado em `applied`)."""
    given = explicit(answer)
    if given is not None:
        return given
    default = REQUEST_DEFAULTS[field]
    applied.append(default)
    return default_answer(default.answer_value)


def endorse(answer: Answer) -> Answer:
    """No pedido mínimo, `true` da pessoa vale sem a frase da carta (a aprovação é humana)."""
    from_letter = answer.source == "carta" and bool((answer.quote or "").strip())
    if answer.value is True and not from_letter:
        return default_answer(True, PERSON_QUOTE)
    return answer


def flag(c: Collector, field: str, answer: Answer | None) -> bool:
    """Booleano de uma resposta explícita; ausente vale `false` e texto vira pendência."""
    given = explicit(answer)
    if given is None:
        return False
    if not isinstance(given.value, bool):
        c.add(field, INVALID_VALUE, _BOOL_TEXT)
        return False
    return given.value
