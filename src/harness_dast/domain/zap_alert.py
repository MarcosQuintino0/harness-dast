"""Alerta bruto do ZAP e a leitura de severidade e confiança.

Os campos e os nomes vêm do spike do M0 (Q5): `pluginId`, `alertRef` (inclui a sub-regra, como
`40014-2`), `cweid`, `wascid`, `risk`, `confidence`, `method`, `url` (a URL ATACADA, mutada),
`param`, `attack`, `evidence`, `inputVector`, `messageId` (a mensagem do ataque) e
`sourceMessageId` (a mensagem aprendida). Severidade e confiança são as que o ZAP PROPÕE: a CLI
só as lê, nunca as altera. Este módulo é puro.
"""

from collections.abc import Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["high", "medium", "low", "informational", "unknown"]
Confidence = Literal["high", "medium", "low", "confirmed", "false_positive", "unknown"]

SEVERITY_RANK: Final[dict[str, int]] = {
    "high": 4,
    "medium": 3,
    "low": 2,
    "informational": 1,
    "unknown": 0,
}
_CONFIDENCE_RANK: Final[dict[str, int]] = {
    "confirmed": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "false_positive": 0,
    "unknown": 0,
}
_SEVERITY_WORDS: Final[dict[str, Severity]] = {
    "high": "high",
    "medium": "medium",
    "low": "low",
    "informational": "informational",
    "info": "informational",
}
_CONFIDENCE_WORDS: Final[dict[str, Confidence]] = {
    "high": "high",
    "medium": "medium",
    "low": "low",
    "confirmed": "confirmed",
    "user confirmed": "confirmed",
    "false positive": "false_positive",
}


class RawAlert(BaseModel):
    """Alerta como o ZAP o devolve (`alert/view/alerts`); todos os campos são texto.

    Attributes:
        id: Identificador do alerta na sessão do ZAP.
        plugin_id: Regra que o gerou.
        alert_ref: Regra com sub-regra (`40014-2`).
        name: Nome do alerta.
        cwe_id: CWE (`-1` ou vazio = sem).
        wasc_id: WASC.
        risk: Severidade proposta pelo ZAP.
        confidence: Confiança proposta pelo ZAP.
        method: Método do ataque.
        url: URL atacada (mutada; não serve de identidade).
        param: Parâmetro atacado.
        attack: Carga enviada.
        evidence: Trecho que o ZAP aponta como prova.
        input_vector: Onde a entrada foi injetada (`json`, `urlpath`, vazio).
        message_id: Mensagem do ataque.
        source_message_id: Mensagem aprendida de onde o ataque partiu.
        description: Descrição padrão do ZAP.
        solution: Solução padrão do ZAP.
    """

    model_config = ConfigDict(
        frozen=True, extra="ignore", populate_by_name=True, coerce_numbers_to_str=True
    )

    id: str = ""
    plugin_id: str = Field(default="", alias="pluginId")
    alert_ref: str = Field(default="", alias="alertRef")
    name: str = Field(default="", alias="alert")
    cwe_id: str = Field(default="", alias="cweid")
    wasc_id: str = Field(default="", alias="wascid")
    risk: str = ""
    confidence: str = ""
    method: str = ""
    url: str = ""
    param: str = ""
    attack: str = ""
    evidence: str = ""
    input_vector: str = Field(default="", alias="inputVector")
    message_id: str = Field(default="", alias="messageId")
    source_message_id: str = Field(default="", alias="sourceMessageId")
    description: str = ""
    solution: str = ""


def parse_severity(risk: str) -> Severity:
    """Lê a severidade proposta (`High`, `High (Medium)`...); texto desconhecido vira `unknown`."""
    word = risk.strip().lower().split(" ", 1)[0]
    return _SEVERITY_WORDS.get(word, "unknown")


def parse_confidence(confidence: str) -> Confidence:
    """Lê a confiança proposta; texto desconhecido vira `unknown`."""
    return _CONFIDENCE_WORDS.get(confidence.strip().lower(), "unknown")


def confidence_rank(value: Confidence) -> int:
    """Ordem de confiança (maior = mais confiável)."""
    return _CONFIDENCE_RANK[value]


def int_or_none(text: str) -> int | None:
    """Converte o texto em inteiro positivo; vazio, `-1` ou inválido dão `None`."""
    stripped = text.strip()
    return (
        int(stripped) if stripped.isascii() and stripped.isdigit() and int(stripped) > 0 else None
    )


def evidence_candidates(alerts: Sequence[RawAlert], cap: int) -> tuple[int, ...]:
    """Ids de mensagem cuja evidência vale buscar: os mais graves e confiáveis primeiro.

    Limita-se a `cap` mensagens distintas para que uma varredura barulhenta não encha o disco.
    """
    ranked = sorted(
        alerts,
        key=lambda a: (
            -SEVERITY_RANK[parse_severity(a.risk)],
            -_CONFIDENCE_RANK[parse_confidence(a.confidence)],
            int_or_none(a.id) or 0,
        ),
    )
    seen: dict[int, None] = {}
    for alert in ranked:
        message_id = int_or_none(alert.message_id)
        if message_id is not None and message_id not in seen:
            seen[message_id] = None
        if len(seen) >= cap:
            break
    return tuple(seen)
