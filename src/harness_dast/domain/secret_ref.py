"""Referência a segredo e a base dos modelos do perfil.

O perfil nunca guarda um segredo, só o NOME de onde buscá-lo. Quem resolve o valor é um
adaptador fora do domínio, nunca o agente.
"""

import re

from pydantic import BaseModel, ConfigDict, field_validator

RESERVED_PREFIX = "HDAST_"
_SECRET_REF = re.compile(r"env:[A-Z][A-Z0-9_]{0,127}")


class ProfileModel(BaseModel):
    """Base dos modelos do perfil: congelados, sem campos extras e sem eco do valor recebido.

    `extra="forbid"` faz um erro de digitação falhar em vez de ser ignorado em silêncio.
    `hide_input_in_errors` impede que o pydantic copie o valor recebido para o texto do erro,
    o que vazaria um segredo digitado no lugar errado.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class SecretRef(ProfileModel):
    """Referência a um segredo, no formato `{secret_ref: "env:NOME"}`.

    Só a forma `env:NOME` é aceita, com NOME em maiúsculas, dígitos e `_`, e sem o prefixo
    `HDAST_` (variáveis do próprio harness, como a chave da API do ZAP). Um valor
    literal (senha, token) não tem como passar: não casa com o formato, e a mensagem de
    erro NÃO repete o que foi informado.

    Attributes:
        secret_ref: A referência, por exemplo `env:AGENDA_USER_A_SENHA`.
    """

    secret_ref: str

    @field_validator("secret_ref")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        """Aceita somente `env:NOME`; nunca devolve nem cita o valor recebido."""
        if not _SECRET_REF.fullmatch(value):
            raise ValueError(
                "referência de segredo inválida; use o formato env:NOME, com NOME em "
                "maiúsculas, dígitos e '_' (o valor do segredo nunca vai no perfil)"
            )
        if value.removeprefix("env:").startswith(RESERVED_PREFIX):
            raise ValueError(
                f"variáveis {RESERVED_PREFIX}* são do próprio harness (chave do ZAP, pastas, "
                "proxy) e não podem ser segredo de um produto; use um nome do produto, "
                "como MEU_PRODUTO_USER_A_SENHA"
            )
        return value

    @property
    def env_name(self) -> str:
        """Nome da variável de ambiente a ser lida por quem resolve o segredo."""
        return self.secret_ref.removeprefix("env:")
