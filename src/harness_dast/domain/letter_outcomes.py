"""Classes de resposta do `probe` que a varredura também ataca, lidas da carta (ADR 0050).

A resposta `attack.include_outcomes` vira `scan.include_outcomes` do perfil. Não amplia escopo,
método, limite, janela nem conta: só quanto se ataca do que já é permitido. Por isso aceita
`source: carta` ou `source: pessoa`, sem frase de origem (diferente de `allow_authz_writes`), e a
aprovação humana mostra a lista. Ausente, nulo, `desconhecido` e lista vazia valem `[]`, sem
pendência. Este módulo é puro.
"""

from typing import Final

from harness_dast.domain.letter import Answer
from harness_dast.domain.letter_collect import INVALID_VALUE, Collector
from harness_dast.domain.scan_config import EXTRA_OUTCOMES

_ORDER: Final = ("logical_failure", "validation_error", "conflict", "not_found", "client_error")
_INVALID_TEXT: Final = (
    "Responda uma lista com classes de: " + ", ".join(_ORDER) + ". Texto solto, classe de "
    "outro tipo ou fora desta lista não vale; na dúvida, responda desconhecido (vale lista vazia)."
)


def read_include_outcomes(c: Collector, answer: Answer | None) -> tuple[str, ...]:
    """Classes extras a varrer; vazio por padrão (ADR 0050).

    Valor que não é lista, classe desconhecida ou que não é texto: pendência `INVALID_VALUE`
    (a mensagem não repete o valor) e nada é permitido. Repetição é deduplicada; a ordem de saída
    é a da lista fechada.
    """
    value = c.take("attack.include_outcomes", answer, required=False)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item in EXTRA_OUTCOMES for item in value
    ):
        c.add("attack.include_outcomes", INVALID_VALUE, _INVALID_TEXT)
        return ()
    return tuple(name for name in _ORDER if name in value)
