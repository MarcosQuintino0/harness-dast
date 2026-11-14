"""Bloco opcional `authz` do `target.yml`: como o teste de autorização entre contas se comporta.

Tudo é declarativo e nada aqui amplia escopo, métodos permitidos pelo escopo, limites ou janela
(o `ScopeGuard` continua decidindo). Mas `vertical_methods` e `mass_assignment_fields` escrevem
no alvo, e `public_operations`, `disabled_checks` e `volatile_fields` escondem achados: por isso
o bloco inteiro entra na impressão digital da aprovação humana (ADR 0037). Sem o bloco, valem os
padrões conservadores abaixo. Este módulo é puro.
"""

import re
from collections.abc import Sequence
from typing import Final, Literal, Self

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from harness_dast.domain.api_model import safe_identifier
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.secret_ref import ProfileModel

AuthzCheck = Literal["horizontal", "excessive_data", "vertical", "mass_assignment"]
CHECK_ORDER: Final[tuple[AuthzCheck, ...]] = (
    "horizontal",
    "excessive_data",
    "vertical",
    "mass_assignment",
)
"""Ordem de execução: do que não escreve no alvo para o que escreve."""

VERTICAL_METHODS_ALLOWED: Final = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH"})
DEFAULT_VERTICAL_METHODS: Final = ("GET", "HEAD")
DEFAULT_VOLATILE_FIELDS: Final = (
    "timestamp",
    "servertime",
    "requestid",
    "traceid",
    "correlationid",
    "date",
    "now",
    "elapsed",
    "elapsedms",
    "etag",
    "nonce",
)
"""Nomes (minúsculas, sem separador) ignorados ao comparar respostas, além dos do perfil."""

MAX_MASS_FIELDS: Final = 10
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
_ROLE = re.compile(r"[^\s]{1,64}")


def normalize_field_name(name: str) -> str:
    """Nome em minúsculas e sem separadores (`requestId`, `request_id` e `request-id` coincidem)."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


class MassAssignmentField(ProfileModel):
    """Campo extra enviado na verificação de atribuição em massa.

    Attributes:
        name: Nome do campo no corpo JSON.
        value: Valor de teste (texto, inteiro ou booleano).
    """

    name: str
    value: StrictStr | StrictInt | StrictBool

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Aceita só nomes simples de campo."""
        if not _NAME.fullmatch(value):
            raise ValueError("nome de campo inválido; use letras, dígitos e '_'")
        return value


DEFAULT_MASS_FIELDS: Final = (
    MassAssignmentField(name="role", value="admin"),
    MassAssignmentField(name="papel", value="admin"),
    MassAssignmentField(name="admin", value=True),
    MassAssignmentField(name="isAdmin", value=True),
)


class AuthzConfig(ProfileModel):
    """Configuração do teste de autorização entre contas.

    Attributes:
        public_operations: `operationId` legitimamente públicos ou compartilhados entre contas;
            BOLA e BFLA os ignoram (sem isso, um recurso público viraria alarme falso).
        role_order: Papéis do MENOR para o MAIOR privilégio (os `role` de `auth.accounts`).
            Necessário para a verificação vertical; sem ele ela diz que não pôde testar.
        volatile_fields: Nomes de campo ignorados na comparação de respostas, além dos padrões.
        vertical_methods: Métodos repetidos na verificação vertical. `DELETE` nunca.
        mass_assignment_fields: Campos extras (e valor de teste) da atribuição em massa.
        disabled_checks: Verificações desligadas pelo perfil.
    """

    public_operations: tuple[str, ...] = Field(default=(), max_length=200)
    role_order: tuple[str, ...] = Field(default=(), max_length=20)
    volatile_fields: tuple[str, ...] = Field(default=(), max_length=50)
    vertical_methods: tuple[str, ...] = DEFAULT_VERTICAL_METHODS
    mass_assignment_fields: tuple[MassAssignmentField, ...] = Field(
        default=DEFAULT_MASS_FIELDS, max_length=MAX_MASS_FIELDS
    )
    disabled_checks: tuple[AuthzCheck, ...] = ()

    @field_validator("role_order")
    @classmethod
    def validate_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Papéis sem repetição e sem espaço."""
        if len(set(value)) != len(value) or not all(_ROLE.fullmatch(role) for role in value):
            raise ValueError("role_order precisa de papéis únicos, sem espaço")
        return value

    @field_validator("volatile_fields")
    @classmethod
    def validate_volatile(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Nomes simples de campo."""
        if not all(_NAME.fullmatch(name) for name in value):
            raise ValueError("nome de campo volátil inválido; use letras, dígitos e '_'")
        return value

    @field_validator("vertical_methods")
    @classmethod
    def validate_methods(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Só métodos liberados; DELETE e desconhecidos são recusados."""
        if not value or not set(value) <= VERTICAL_METHODS_ALLOWED:
            raise ValueError(
                "vertical_methods aceita só GET, HEAD, POST, PUT e PATCH (nunca DELETE)"
            )
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def validate_unique_fields(self) -> Self:
        """Campos extras sem repetição."""
        names = [item.name for item in self.mass_assignment_fields]
        if len(set(names)) != len(names):
            raise ValueError("campo repetido em mass_assignment_fields")
        return self

    def volatile_names(self) -> frozenset[str]:
        """Nomes ignorados na comparação (padrões mais os do perfil), normalizados."""
        extra = (normalize_field_name(name) for name in self.volatile_fields)
        return frozenset((*DEFAULT_VOLATILE_FIELDS, *extra))

    def enabled_checks(self, requested: Sequence[AuthzCheck] = ()) -> tuple[AuthzCheck, ...]:
        """Verificações a rodar, na ordem fixa: as pedidas (ou todas) menos as desligadas."""
        wanted = tuple(requested) or CHECK_ORDER
        return tuple(
            check for check in CHECK_ORDER if check in wanted and check not in self.disabled_checks
        )

    def ensure_operations_exist(self, operation_ids: Sequence[str]) -> None:
        """Garante que toda operação pública citada existe no OpenAPI.

        Raises:
            ConfigError: `operationId` desconhecido.
        """
        known = set(operation_ids)
        for name in self.public_operations:
            if name not in known:
                raise ConfigError(
                    f"authz.public_operations cita a operação {safe_identifier(name)}, "
                    "que não existe no OpenAPI.",
                    hint="Corrija public_operations em authz (veja spec inspect).",
                )
