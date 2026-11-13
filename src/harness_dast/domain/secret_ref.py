"""Referência a segredo e a base dos modelos do perfil.

O perfil nunca guarda um segredo, só o NOME de onde buscá-lo. Quem resolve o valor é um
adaptador fora do domínio, nunca o agente.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

RESERVED_PREFIX = "HDAST_"
SecretKind = Literal["env", "keyring"]
_NAME = r"[A-Z][A-Z0-9_]{0,127}"
_SECRET_REF = re.compile(rf"(?:env|keyring):{_NAME}")
_NAME_ONLY = re.compile(_NAME)


class ProfileModel(BaseModel):
    """Base dos modelos do perfil: congelados, sem campos extras e sem eco do valor recebido.

    `extra="forbid"` faz um erro de digitação falhar em vez de ser ignorado em silêncio.
    `hide_input_in_errors` impede que o pydantic copie o valor recebido para o texto do erro,
    o que vazaria um segredo digitado no lugar errado.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class SecretRef(ProfileModel):
    """Referência a um segredo: `{secret_ref: "env:NOME"}` ou `{secret_ref: "keyring:NOME"}`.

    `env:NOME` lê uma variável de ambiente (caminho do CI e da avaliação cega); `keyring:NOME`
    lê o cofre de credenciais do sistema operacional (ADR 0030). NOME é em maiúsculas, dígitos
    e `_`, sem o prefixo `HDAST_` (variáveis do próprio harness, como a chave da API do ZAP).
    Um valor literal (senha, token) não tem como passar: não casa com o formato, e a mensagem
    de erro NÃO repete o que foi informado.

    Attributes:
        secret_ref: A referência, por exemplo `env:AGENDA_USER_A_SENHA`.
    """

    secret_ref: str

    @field_validator("secret_ref")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        """Aceita somente `env:NOME` ou `keyring:NOME`; nunca devolve nem cita o valor."""
        if not _SECRET_REF.fullmatch(value):
            raise ValueError(
                "referência de segredo inválida; use o formato env:NOME ou keyring:NOME, com "
                "NOME em maiúsculas, dígitos e '_' (o valor do segredo nunca vai no perfil)"
            )
        if value.split(":", 1)[1].startswith(RESERVED_PREFIX):
            raise ValueError(
                f"nomes {RESERVED_PREFIX}* são do próprio harness (chave do ZAP, pastas, "
                "proxy) e não podem ser segredo de um produto; use um nome do produto, "
                "como MEU_PRODUTO_USER_A_SENHA"
            )
        return value

    @property
    def kind(self) -> SecretKind:
        """De onde o valor vem: `env` (variável de ambiente) ou `keyring` (cofre do sistema)."""
        return "keyring" if self.secret_ref.startswith("keyring:") else "env"

    @property
    def name(self) -> str:
        """NOME depois do prefixo (nome da variável ou nome da credencial no cofre)."""
        return self.secret_ref.split(":", 1)[1]

    @property
    def env_name(self) -> str:
        """Nome da variável de ambiente a ser lida por quem resolve o segredo.

        Raises:
            ValueError: Se a referência é do cofre. Ler um `keyring:` do ambiente seria cair em
                silêncio em outro lugar; é erro de quem chamou.
        """
        if self.kind != "env":
            raise ValueError("a referência não é env:NOME; use o resolvedor do cofre")
        return self.name


def is_valid_secret_name(name: str) -> bool:
    """Diz se `name` serve como NOME de segredo do cofre (formato e sem prefixo `HDAST_`)."""
    return bool(_NAME_ONLY.fullmatch(name)) and not name.startswith(RESERVED_PREFIX)
