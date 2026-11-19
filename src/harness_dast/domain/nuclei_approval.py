"""Apresentação das autorizações do Nuclei para revisão humana (ADR 0122)."""

from typing import Final

from harness_dast.domain import nuclei_version
from harness_dast.domain.nuclei_permissions import nuclei_permissions
from harness_dast.domain.profile import ProductProfile

NUCLEI_INACTIVE_OPTIONS: Final = (
    "Nuclei: as opções de login e caminhos amplos marcadas no perfil ficam sem efeito "
    "com o motor desautorizado."
)
NUCLEI_WIDE_PATHS_LINE: Final = (
    "O Nuclei pode consultar qualquer caminho das origens aprovadas, mesmo fora do Swagger. "
    "Os caminhos negados continuam negados."
)


def _word(value: bool) -> str:
    return "sim" if value else "não"


def describe_nuclei(profile: ProductProfile) -> tuple[str, ...]:
    """Descreve as permissões do Nuclei, com aviso quando só as opções auxiliares foram marcadas.

    Escrita e apagar vêm das permissões que já existem (`nuclei_permissions`).
    """
    checks = profile.extra_checks
    if not checks.nuclei:
        return (NUCLEI_INACTIVE_OPTIONS,) if checks.nuclei_login or checks.nuclei_wide_paths else ()
    allowed = nuclei_permissions(profile)
    lines: tuple[str, ...] = (
        f"Nuclei: verificações conhecidas da comunidade, versão "
        f"{nuclei_version.TEMPLATES_VERSION} dos modelos. "
        f"Com login: {_word(allowed.login)}. "
        f"Endereços fora do Swagger: {_word(checks.nuclei_wide_paths)}. "
        f"Escrita: {_word(allowed.writes)}. Apagar: {_word(allowed.delete)}.",
    )
    if checks.nuclei_wide_paths:
        lines += (NUCLEI_WIDE_PATHS_LINE,)
    return lines
