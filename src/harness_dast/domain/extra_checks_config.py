"""Autorizações adicionais do perfil, desligadas por padrão (ADRs 0096 e 0122)."""

from typing import Final

from pydantic import StrictBool

from harness_dast.domain.secret_ref import ProfileModel

NUCLEI_FIELDS: Final = ("nuclei", "nuclei_login", "nuclei_wide_paths")
"""Chaves da declaração de autorização do Nuclei na carta e no perfil."""


class ExtraChecksConfig(ProfileModel):
    """Permissões das capacidades extras, todas desligadas por padrão.

    Attributes:
        allow_rate_tests: Testes de limite de consumo (poucos pedidos, com teto rígido).
        experimental_rules: Regras experimentais (alpha) do ZAP, achados marcados como tal.
        inventory: Inventário de versões irmãs e documentação exposta, só no escopo.
        nuclei: Autorização declarada para o Nuclei.
        nuclei_login: Autorização declarada para login com o Nuclei.
        nuclei_wide_paths: Autorização declarada para caminhos fora do Swagger com o Nuclei.
    """

    allow_rate_tests: StrictBool = False
    experimental_rules: StrictBool = False
    inventory: StrictBool = False
    nuclei: StrictBool = False
    nuclei_login: StrictBool = False
    nuclei_wide_paths: StrictBool = False

    def is_default(self) -> bool:
        """Se o bloco vale o padrão (a impressão digital o deixa de fora, ADR 0096)."""
        return self == type(self)()
