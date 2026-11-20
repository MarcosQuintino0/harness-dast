"""Transcrição conservadora da declaração consultiva de tecnologias da carta."""

from harness_dast.domain.letter import Answer
from harness_dast.domain.letter_collect import Collector
from harness_dast.domain.technology import TechnologyDeclaration


def read_technologies(c: Collector, answer: Answer | None) -> TechnologyDeclaration | None:
    """Recusa declaração preenchida sem origem e frase da carta; ausente não altera perfil."""
    field = "attack.technologies"
    value = c.take(field, answer, required=False)
    if value is None:
        return None
    if not isinstance(value, list):
        c.add(field, "INVALID_VALUE", "Informe uma lista de tecnologias.")
        return None
    if not value:
        return None
    if answer is None or answer.source != "carta" or not (answer.quote or "").strip():
        c.add(field, "TECHNOLOGIES_NEED_LETTER", "Use source: carta e copie a frase em quote.")
        return None
    return c.check_model(
        field,
        TechnologyDeclaration,
        {
            "value": value,
            "source": answer.source,
            "quote": answer.quote,
        },
        {},
    )
