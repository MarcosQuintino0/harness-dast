"""Avisos em destaque que o `hdast setup` põe antes do resumo da aprovação (ADR 0114).

A pessoa só aprova o que viu: por isso o que a CLI preencheu por padrão e a ausência de caminho
proibido aparecem no alto do resumo, e não escondidos entre as outras linhas. Este módulo é puro.
"""

from harness_dast.domain.profile import ProductProfile


def approval_notes(profile: ProductProfile, applied_defaults: tuple[str, ...]) -> tuple[str, ...]:
    """Linhas de destaque para o resumo da aprovação; vazio quando não há o que destacar.

    Args:
        profile: Perfil que a pessoa vai aprovar.
        applied_defaults: Padrões mínimos aplicados na carta, como `campo = valor`.

    Returns:
        Avisos de nenhum caminho proibido e dos padrões mínimos da CLI.
    """
    notes: list[str] = []
    if not profile.scope.deny_paths:
        notes.append(
            "ATENÇÃO: nenhum caminho proibido foi declarado (scope.deny_paths vazio). "
            "Confirme com o dono do produto que não há caminho a excluir."
        )
    if applied_defaults:
        notes.append("PADRÃO MÍNIMO DA CLI (resposta 'não sei' na carta, sem valor de ninguém):")
        notes.extend(f"  - {item}" for item in applied_defaults)
    return tuple(notes)
