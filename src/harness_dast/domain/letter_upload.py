"""Permissão da varredura de envio de arquivo, lida da carta (ADR 0052).

Varrer com o ZAP uma operação `multipart/form-data` grava no armazenamento do alvo o conteúdo de
ataque do varredor (nome e conteúdo de arquivo, campos de texto). Isso só vale se a carta
assinada o autorizar. Este módulo confere a resposta `attack.allow_upload_scan` e devolve um
booleano: `false` por padrão e `true` só com origem `carta` e a frase de origem. É o mesmo molde
de `letter_writes` e `letter_negative`, com campo próprio. É puro.
"""

from harness_dast.domain.letter import Answer
from harness_dast.domain.letter_collect import (
    INVALID_VALUE,
    UPLOAD_SCAN_NEEDS_LETTER,
    Collector,
)

_FIELD = "attack.allow_upload_scan"


def read_allow_upload_scan(c: Collector, answer: Answer | None) -> bool:
    """Se o `scan` pode varrer operações de envio de arquivo; `false` por padrão (ADR 0052).

    Ausente, nulo e `desconhecido` valem `false` sem pendência. `true` só passa com origem
    `carta` e a frase de origem: o agente nunca liga a varredura de upload por conta própria.
    Valor que não é booleano é recusado (nunca vira `true` por engano, como o texto "sim").
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
            UPLOAD_SCAN_NEEDS_LETTER,
            "Varrer com o ZAP uma operação de envio de arquivo grava conteúdo de ataque no "
            "armazenamento do alvo; só vale se a carta assinada o autorizar: use source: carta e "
            "copie em quote a frase da carta. O agente nunca liga por conta própria; na dúvida, "
            "responda desconhecido (vale false).",
        )
        return False
    return True
