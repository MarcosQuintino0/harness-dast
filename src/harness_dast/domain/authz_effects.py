"""Construção conservadora de recibo estrutural após efeito relido pela conta escritora."""

from pydantic import ValidationError

from harness_dast.domain.authz_sensitive import classify_field_name
from harness_dast.domain.knowledge import KnowledgeEffect


def verified_effect(
    write_operation: str, read_operation: str, account: str, fields: tuple[str, ...]
) -> KnowledgeEffect | None:
    """Valida nomes sem ecoar entrada; nunca guarda valores, ID ou resposta."""
    if any(classify_field_name(field) != "plain" for field in fields):
        return None
    try:
        return KnowledgeEffect(
            write_operation=write_operation,
            read_operation=read_operation,
            account=account,
            fields=fields,
            proof="readback_verified",
        )
    except ValidationError:
        return None
