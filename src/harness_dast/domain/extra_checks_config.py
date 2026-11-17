"""Bloco opcional `extra_checks` do `target.yml`: capacidades da V1.12 só da carta (ADR 0096).

Nada aqui amplia escopo, janela ou limites (o `ScopeGuard` continua decidindo). Mas cada chave
muda o tráfego ou o relato (testes de limite, regras experimentais, inventário de caminhos
irmãos): por isso o bloco entra na impressão digital da aprovação humana quando difere do padrão
e todas as chaves nascem desligadas. Os campos vêm de `attack.*` da carta estruturada; as
capacidades que os consomem chegam em passos posteriores da V1.12. Este módulo é puro.
"""

from pydantic import StrictBool

from harness_dast.domain.secret_ref import ProfileModel


class ExtraChecksConfig(ProfileModel):
    """Permissões das capacidades extras da V1.12, todas desligadas por padrão.

    Attributes:
        allow_rate_tests: Testes de limite de consumo (poucos pedidos, com teto rígido).
        experimental_rules: Regras experimentais (alpha) do ZAP, achados marcados como tal.
        inventory: Inventário de versões irmãs e documentação exposta, só no escopo.
    """

    allow_rate_tests: StrictBool = False
    experimental_rules: StrictBool = False
    inventory: StrictBool = False

    def is_default(self) -> bool:
        """Se o bloco vale o padrão (a impressão digital o deixa de fora, ADR 0096)."""
        return self == type(self)()
