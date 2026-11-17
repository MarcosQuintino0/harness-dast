"""Papéis compartilhados declarados pela carta (ADR 0057)."""

from harness_dast.domain.authz.config import AuthzConfig
from harness_dast.domain.letter import Answer
from harness_dast.domain.letter_collect import INVALID_VALUE, SHARED_ROLES_NEEDS_LETTER, Collector


def read_shared_roles(c: Collector, answer: Answer | None) -> tuple[str, ...]:
    """Lê lista opcional e exige a frase da carta quando preenchida."""
    field = "attack.authz_shared_roles"
    value = c.take(field, answer, required=False)
    if value is None:
        return ()
    if not isinstance(value, list):
        c.add(field, INVALID_VALUE, "Informe uma lista de papéis únicos.")
        return ()
    config = c.check_model("attack.authz_shared_roles", AuthzConfig, {"shared_roles": value}, {})
    if config is None:
        return ()
    if value and (answer is None or answer.source != "carta" or not (answer.quote or "").strip()):
        c.add(field, SHARED_ROLES_NEEDS_LETTER, "Use source: carta e copie a frase em quote.")
        return ()
    return tuple(sorted(config.shared_roles))
