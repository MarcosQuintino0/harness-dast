"""Classifica sinais em respostas já redigidas, sem conservar seu conteúdo."""

import re
from collections.abc import Mapping
from typing import Final

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.redaction import EvidenceMessage

_PATTERNS: Final = {
    "http_5xx": re.compile(r"^HTTP/\d(?:\.\d)?\s+5\d\d(?:\s|$)", re.IGNORECASE),
    "stack_trace": re.compile(
        r"traceback \(most recent call last\)|\bat [\w.$]+\([^\n]*:\d+\)|"
        r"\b(?:[\w]+\.)*[\w]+Exception\s*:",
        re.IGNORECASE,
    ),
    "sql_error": re.compile(
        r"\bSQLSTATE\s*\[?[0-9A-Z]{5}\]?|\bORA-\d{5}\b|"
        r"\b(?:syntax error at or near|unclosed quotation mark after the character string)\b",
        re.IGNORECASE,
    ),
}
SIGNAL_LABELS: Final = {
    "http_5xx": "Resposta HTTP 5xx",
    "stack_trace": "Possível rastreamento de exceção",
    "sql_error": "Possível erro de banco de dados",
}


class InternalErrorSignals(ApiModel):
    """Contagens por mensagem distinta; não são achados confirmados nem cobertura completa.

    Attributes:
        messages_examined: Mensagens distintas disponíveis.
        truncated_messages: Mensagens distintas com algum campo cortado.
        counts: Mensagens distintas por categoria fixa; uma mensagem pode ter várias categorias.
    """

    messages_examined: int
    truncated_messages: int
    counts: dict[str, int]


def classify_internal_error_signals(
    evidence: Mapping[int, EvidenceMessage],
) -> InternalErrorSignals:
    """Conta sinais somente em cabeçalho e corpo de respostas já redigidas.

    Repetições do mesmo identificador de mensagem contam uma vez por categoria. Não devolve
    trechos, identificadores ou outros dados da resposta.
    """
    categories: dict[int, set[str]] = {}
    truncated: set[int] = set()
    for message in evidence.values():
        found = categories.setdefault(message.message_id, set())
        if message.truncated:
            truncated.add(message.message_id)
        for name, pattern in _PATTERNS.items():
            text = (
                message.response_header.split("\n", 1)[0]
                if name == "http_5xx"
                else message.response_body
            )
            if pattern.search(text):
                found.add(name)
    return InternalErrorSignals(
        messages_examined=len(categories),
        truncated_messages=len(truncated),
        counts={name: sum(name in found for found in categories.values()) for name in _PATTERNS},
    )
