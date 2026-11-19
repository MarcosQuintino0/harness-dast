"""Apresentação das autorizações do Nuclei para revisão humana (ADR 0122)."""

from typing import Final

from harness_dast.domain import nuclei_version
from harness_dast.domain.extra_checks_config import ExtraChecksConfig

NUCLEI_INACTIVE_OPTIONS: Final = (
    "Nuclei: as opções de login e caminhos amplos marcadas no perfil ficam sem efeito "
    "com o motor desautorizado."
)


def describe_nuclei(checks: ExtraChecksConfig) -> tuple[str, ...]:
    """Descreve a declaração registrada, com aviso quando só as opções auxiliares foram marcadas."""
    if not checks.nuclei:
        return (NUCLEI_INACTIVE_OPTIONS,) if checks.nuclei_login or checks.nuclei_wide_paths else ()
    login = "sim" if checks.nuclei_login else "não"
    wide_paths = "sim" if checks.nuclei_wide_paths else "não"
    lines: tuple[str, ...] = (
        f"Nuclei: verificações conhecidas da comunidade, versão "
        f"{nuclei_version.TEMPLATES_VERSION} dos modelos. "
        f"Com login: {login}. Endereços fora do Swagger: {wide_paths}.",
    )
    if checks.nuclei_wide_paths:
        lines += (
            "A declaração abrange qualquer caminho das origens aprovadas. "
            "Os caminhos negados continuam negados.",
        )
    return lines
