"""Tabela "quem pode o quê" do bloco `authz` (ADR 0041): o modelo da regra e sua conferência.

A tabela é **declaração humana**: a ferramenta nunca a completa, nunca a aprova e nunca trata
o que não está nela como proibido. Um papel que existe em `auth.accounts` e não aparece em
`allow` nem em `deny` de uma operação é `unspecified` naquela linha e não é testado. Este
módulo só descreve e confere a regra; o plano, o veredito e a tabela do relatório ficam em
`authz_matrix_plan`, `authz_matrix_report` e `report_authz_matrix`. É puro.
"""

import re
from collections.abc import Collection, Sequence
from typing import Final, Self

from pydantic import Field, StrictStr, field_validator, model_validator

from harness_dast.domain.api_model import safe_identifier
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.secret_ref import ProfileModel

MAX_MATRIX_RULES: Final = 500
MAX_ROLES_PER_LIST: Final = 20
MAX_OPERATION_CHARS: Final = 200
_ROLE = re.compile(r"[^\s]{1,64}")


class AuthzConfigError(ConfigError):
    """O bloco `authz` não combina com o OpenAPI ou com as contas do perfil (ADR 0041).

    Mesma saída do erro de configuração (2): nenhum código de saída novo. O `code` próprio
    deixa o agente separar "a tabela cita operação ou papel que não existe" de um YAML mal
    formado.
    """

    code = "AUTHZ_CONFIG_INVALID"


class AccessRule(ProfileModel):
    """Uma linha da tabela: quem pode e quem NÃO pode uma operação.

    Attributes:
        operation: `operationId` do OpenAPI.
        allow: Papéis que podem (a ferramenta não testa permissão, só mostra).
        deny: Papéis que NÃO podem; cada um será testado. Vazio documenta quem pode e a linha
            sai sem teste (`nothing_to_deny`).
    """

    operation: StrictStr = Field(min_length=1, max_length=MAX_OPERATION_CHARS)
    allow: tuple[StrictStr, ...] = Field(default=(), max_length=MAX_ROLES_PER_LIST)
    deny: tuple[StrictStr, ...] = Field(default=(), max_length=MAX_ROLES_PER_LIST)

    @field_validator("allow", "deny")
    @classmethod
    def validate_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Papéis sem repetição e sem espaço (como em `role_order`)."""
        if len(set(value)) != len(value) or not all(_ROLE.fullmatch(role) for role in value):
            raise ValueError("a lista precisa de papéis únicos, sem espaço")
        return value

    @model_validator(mode="after")
    def validate_disjoint(self) -> Self:
        """Um papel não pode estar em `allow` e em `deny` da mesma operação."""
        if set(self.allow) & set(self.deny):
            raise ValueError("um papel não pode estar em allow e em deny da mesma operação")
        return self

    def declared(self, role: str) -> str:
        """`allow`, `deny` ou `unspecified` para o papel nesta linha."""
        if role in self.allow:
            return "allow"
        return "deny" if role in self.deny else "unspecified"


def validate_matrix_rules(rules: Sequence[AccessRule]) -> None:
    """Confere o que depende só da tabela: no máximo 500 regras e uma por operação.

    Raises:
        ValueError: Regras demais ou operação repetida (vira erro de campo do perfil).
    """
    if len(rules) > MAX_MATRIX_RULES:
        raise ValueError(f"access_matrix aceita no máximo {MAX_MATRIX_RULES} regras")
    names = [rule.operation for rule in rules]
    if len(set(names)) != len(names):
        raise ValueError("operação repetida em access_matrix (uma regra por operação)")


def ensure_matrix_valid(
    rules: Sequence[AccessRule],
    public_operations: Collection[str],
    operation_ids: Collection[str],
    roles: Collection[str],
) -> None:
    """Garante que operações e papéis da tabela existem e que nenhuma operação é pública.

    Args:
        rules: A tabela do perfil.
        public_operations: `authz.public_operations`.
        operation_ids: `operationId` do OpenAPI.
        roles: Papéis (`role`) das contas de `auth.accounts`.

    Raises:
        AuthzConfigError: Operação fora do OpenAPI, papel sem conta, ou operação que também
            está em `public_operations` (contradição). A mensagem cita o nome, nunca valor
            de segredo.
    """
    for rule in rules:
        name = safe_identifier(rule.operation)
        if rule.operation not in operation_ids:
            raise AuthzConfigError(
                f"authz.access_matrix cita a operação {name}, que não existe no OpenAPI.",
                hint="Corrija o nome da operação em access_matrix (veja spec inspect).",
            )
        if rule.operation in public_operations:
            raise AuthzConfigError(
                f"authz.access_matrix e authz.public_operations citam a mesma operação {name}.",
                hint="Uma operação pública não tem 'quem não pode': tire-a de um dos dois.",
            )
        for role in (*rule.allow, *rule.deny):
            if role not in roles:
                raise AuthzConfigError(
                    f"authz.access_matrix cita o papel {safe_identifier(role)} na operação "
                    f"{name}, mas nenhuma conta de auth.accounts tem esse papel.",
                    hint="Corrija o papel ou cadastre uma conta com ele em auth.accounts.",
                )
