"""Permissão de escrita do teste de valores inválidos, lida da carta (ADR 0051).

Gravar no ambiente um dado com valor que o contrato proíbe (`POST`, `PUT` e `PATCH`) só vale se a
carta assinada o autorizar. Este módulo confere a resposta `attack.allow_invalid_input_writes` e
devolve um booleano: `false` por padrão e `true` só com origem `carta` e a frase de origem. É o
mesmo molde de `letter_writes` (ADR 0038), com campo próprio: a pergunta de lá é se o teste
ENTRE CONTAS pode escrever; esta é se o teste pode gravar dado INVÁLIDO. É puro.
"""

from harness_dast.domain.letter import Answer
from harness_dast.domain.letter_collect import (
    INVALID_VALUE,
    NEGATIVE_WRITES_NEEDS_LETTER,
    Collector,
)

_FIELD = "attack.allow_invalid_input_writes"


def read_allow_invalid_writes(c: Collector, answer: Answer | None) -> bool:
    """Se o teste negativo pode escrever dado inválido no alvo; `false` por padrão (ADR 0051).

    Ausente, nulo e `desconhecido` valem `false` sem pendência. `true` só passa com origem
    `carta` e a frase de origem: o agente nunca liga a escrita por conta própria. Valor que não é
    booleano é recusado (nunca vira `true` por engano, como o texto "sim").
    """
    value = c.take(_FIELD, answer, required=False)
    if value is None or value is False:
        return False
    if value is not True:
        c.add(_FIELD, INVALID_VALUE, "Responda true (sim) ou false (não).")
        return False
    from_letter = answer is not None and answer.source == "carta"
    quote = answer.quote if answer is not None else None
    if not from_letter or not (quote or "").strip():
        c.add(
            _FIELD,
            NEGATIVE_WRITES_NEEDS_LETTER,
            "Gravar dado com valor inválido no ambiente só vale se a carta assinada o autorizar: "
            "use source: carta e copie em quote a frase da carta. O agente nunca liga por conta "
            "própria; na dúvida, responda desconhecido (vale false).",
        )
        return False
    return True
