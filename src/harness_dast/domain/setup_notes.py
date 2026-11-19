"""Destaques para a pessoa revisar no início do resumo do `hdast setup`."""

from harness_dast.domain.nuclei_approval import describe_nuclei
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.request_defaults import SETUP_LABEL
from harness_dast.domain.scope_approval_summary import describe_environment, describe_schedule

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _denied_paths(profile: ProductProfile) -> tuple[str, ...]:
    if not profile.scope.deny_paths:
        return (
            "ATENÇÃO: nenhum caminho proibido foi declarado (scope.deny_paths vazio). "
            "Confirme com o dono do produto que não há caminho a excluir.",
        )
    return ("CAMINHOS NEGADOS", *(f"  - {path}" for path in profile.scope.deny_paths))


def _enabled_capabilities(profile: ProductProfile) -> tuple[str, ...]:
    scan, checks = profile.scan, profile.extra_checks
    flags = (
        ("scan.inject_headers", scan.inject_headers),
        ("scan.oast", scan.oast),
        ("extra_checks.allow_rate_tests", checks.allow_rate_tests),
        ("extra_checks.experimental_rules", checks.experimental_rules),
        ("extra_checks.inventory", checks.inventory),
    )
    lines = [f"  - {name}" for name, enabled in flags if enabled]
    if scan.include_outcomes:
        lines.append("  - scan.include_outcomes = " + ", ".join(scan.include_outcomes))
    return ("CAPACIDADES ADICIONAIS LIGADAS", *lines) if lines else ()


def _write_notes(profile: ProductProfile) -> tuple[str, ...]:
    methods = {method for rule in profile.scope.allow for method in rule.methods}
    writes = ", ".join(sorted(methods & _WRITE_METHODS)) or "nenhum declarado"
    flags = (
        ("Escrita entre contas (authz.allow_writes)", profile.authz.allow_writes),
        ("Escrita de valores inválidos (negative.allow_writes)", profile.negative.allow_writes),
        ("Varredura de envio de arquivos (scan.allow_upload_scan)", profile.scan.allow_upload_scan),
        ("Limpeza configurada (cleanup)", profile.cleanup is not None),
    )
    return (
        "OPERAÇÕES QUE PODEM GRAVAR NO AMBIENTE",
        f"  - Métodos de escrita em scope.allow: {writes}",
        *(f"  - {label}: {'sim' if enabled else 'não'}" for label, enabled in flags),
    )


def approval_notes(profile: ProductProfile, applied_defaults: tuple[str, ...]) -> tuple[str, ...]:
    """Mostra os destaques do perfil em revisão e os padrões aplicados pela CLI.

    Args:
        profile: Perfil que a pessoa vai aprovar.
        applied_defaults: Padrões aplicados na carta, como `campo = valor`. Os do pedido mínimo
            (ADR 0120) vêm com o prefixo `request_defaults.SETUP_LABEL`; os demais são os padrões
            mínimos da resposta "não sei" (ADR 0114).

    Returns:
        Linhas para o terminal, sem alterar o perfil nem o resumo gravado na aprovação.
    """
    requested = tuple(
        item.removeprefix(SETUP_LABEL) for item in applied_defaults if item.startswith(SETUP_LABEL)
    )
    minimum = tuple(item for item in applied_defaults if not item.startswith(SETUP_LABEL))
    notes = [
        "ENDEREÇO DO AMBIENTE",
        f"  {describe_environment(profile)}",
        *_denied_paths(profile),
        *_enabled_capabilities(profile),
        *describe_nuclei(profile),
        *_write_notes(profile),
        "VALIDADE E JANELAS DE EXECUÇÃO",
        *(f"  {line}" for line in describe_schedule(profile)),
    ]
    if requested:
        notes.append("PADRÕES DO PEDIDO MÍNIMO (a CLI aplicou; ninguém respondeu estes campos):")
        notes.extend(f"  - {item}" for item in requested)
    if minimum:
        notes.append("PADRÃO MÍNIMO DA CLI (resposta 'não sei' na carta, sem valor de ninguém):")
        notes.extend(f"  - {item}" for item in minimum)
    return tuple(notes)
