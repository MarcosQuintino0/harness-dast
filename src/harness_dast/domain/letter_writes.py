"""Permissão de escrita do teste de autorização entre contas, lida da carta (ADR 0038).

A escrita no alvo (atribuição em massa, alteração de recurso de outra conta e métodos de escrita
da verificação vertical e da tabela quem pode o quê) só vale se a carta assinada a autorizar.
Este módulo confere a resposta `attack.allow_authz_writes` e devolve um booleano: `false` por
padrão e `true` só com origem `carta` e a frase de origem. É puro.
"""

from harness_dast.domain.letter import Answer
from harness_dast.domain.letter_collect import AUTHZ_WRITES_NEEDS_LETTER, INVALID_VALUE, Collector


def read_allow_writes(c: Collector, answer: Answer | None) -> bool:
    """Se o teste entre contas pode escrever no alvo; `false` por padrão (ADR 0038).

    Ausente, nulo e `desconhecido` valem `false` sem pendência. `true` só passa com origem
    `carta` e a frase de origem: o agente nunca liga a escrita por conta própria. Valor que não é
    booleano é recusado (nunca vira `true` por engano, como o texto "sim").
    """
    value = c.take("attack.allow_authz_writes", answer, required=False)
    if value is None or value is False:
        return False
    if value is not True:
        c.add("attack.allow_authz_writes", INVALID_VALUE, "Responda true (sim) ou false (não).")
        return False
    from_letter = answer is not None and answer.source == "carta"
    quote = answer.quote if answer is not None else None
    if not from_letter or not (quote or "").strip():
        c.add(
            "attack.allow_authz_writes",
            AUTHZ_WRITES_NEEDS_LETTER,
            "A escrita do teste entre contas só vale se a carta assinada a autorizar: use "
            "source: carta e copie em quote a frase da carta. O agente nunca a liga por conta "
            "própria; na dúvida, responda desconhecido (vale false).",
        )
        return False
    return True
