"""Qual conta envia cada operação (`auth.default_account` e `auth.account_map`).

O agente só cita APELIDOS de conta; nunca vê usuário nem senha. Cada regra de `account_map`
escolhe uma conta para as operações que casam com TODOS os critérios que ela declara:

- `operations`: o `operationId` está na lista;
- `path`: o caminho da operação casa com o padrão (mesma gramática de `scope.allow[].paths`;
  os `{marcadores}` do OpenAPI valem como um segmento qualquer);
- `methods`: o método está na lista (só com `path`).

A primeira regra que casa vence; sem regra, vale `default_account`, e sem ele a primeira conta
de `auth.accounts`. Este módulo é puro.
"""

import re
from collections.abc import Sequence

from pydantic import Field, field_validator, model_validator

from harness_dast.domain.api_model import safe_identifier
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.pathpattern import matches, parse_pattern
from harness_dast.domain.secret_ref import ProfileModel
from harness_dast.domain.urlnorm import KNOWN_METHODS

MAX_ACCOUNT_RULES = 100
_PLACEHOLDER = re.compile(r"\{[^{}/]+\}")
_NEUTRAL_SEGMENT = "x"
_ALIAS = re.compile(r"[a-z][a-z0-9_]{0,31}")


class AccountRule(ProfileModel):
    """Uma regra do mapa de contas.

    Attributes:
        account: Apelido da conta (precisa existir em `auth.accounts`).
        operations: `operationId` do OpenAPI atendidos pela regra.
        path: Padrão de caminho (`/api/receitas/**`) atendido pela regra.
        methods: Métodos HTTP em maiúsculas; só vale junto de `path`.
    """

    account: str
    operations: tuple[str, ...] = Field(default=(), max_length=200)
    path: str | None = None
    methods: tuple[str, ...] = ()

    @field_validator("account")
    @classmethod
    def validate_account(cls, value: str) -> str:
        """Aceita só apelido no formato das contas."""
        if not _ALIAS.fullmatch(value):
            raise ValueError("apelido de conta inválido; use minúsculas, dígitos e '_'")
        return value

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        """Confere o padrão de caminho com a gramática do escopo."""
        if value is not None:
            parse_pattern(value)
        return value

    @field_validator("methods")
    @classmethod
    def validate_methods(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Aceita só métodos conhecidos, em maiúsculas."""
        if not set(value) <= KNOWN_METHODS:
            raise ValueError("método HTTP desconhecido ou fora de maiúsculas")
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def validate_criteria(self) -> "AccountRule":
        """Exige ao menos `operations` ou `path`, e `methods` só com `path`."""
        if not self.operations and self.path is None:
            raise ValueError("a regra precisa de 'operations' ou de 'path'")
        if self.methods and self.path is None:
            raise ValueError("'methods' só vale junto de 'path'")
        return self

    def covers(self, operation_id: str, method: str, path: str) -> bool:
        """Diz se a operação casa com todos os critérios declarados."""
        if self.operations and operation_id not in self.operations:
            return False
        if self.methods and method.upper() not in self.methods:
            return False
        if self.path is None:
            return True
        segments = tuple(_PLACEHOLDER.sub(_NEUTRAL_SEGMENT, path).strip("/").split("/"))
        return matches(parse_pattern(self.path), segments if segments != ("",) else ())


class AccountRouting(ProfileModel):
    """Campos de roteamento de contas, herdados pelos dois tipos de `auth`.

    Attributes:
        default_account: Conta das operações que nenhuma regra atende; sem ela, a primeira.
        account_map: Regras, avaliadas em ordem.
    """

    default_account: str | None = None
    account_map: tuple[AccountRule, ...] = Field(default=(), max_length=MAX_ACCOUNT_RULES)

    def ensure_known_accounts(self, aliases: Sequence[str]) -> None:
        """Garante que toda conta citada existe.

        Raises:
            ValueError: Apelido desconhecido (a mensagem lista os válidos).
        """
        known = set(aliases)
        cited = [self.default_account] if self.default_account else []
        cited.extend(rule.account for rule in self.account_map)
        for alias in cited:
            if alias not in known:
                raise ValueError(
                    f"a conta '{alias}' citada no roteamento não existe em accounts "
                    f"(válidas: {', '.join(aliases)})"
                )

    def route(self, aliases: Sequence[str], operation_id: str, method: str, path: str) -> str:
        """Apelido da conta que envia a operação.

        Args:
            aliases: Apelidos de `accounts`, na ordem do perfil.
            operation_id: `operationId` da operação.
            method: Método HTTP.
            path: Modelo de caminho do OpenAPI.
        """
        for rule in self.account_map:
            if rule.covers(operation_id, method, path):
                return rule.account
        return self.default_account or aliases[0]

    def explicit_account(self, operation_id: str, method: str, path: str) -> str | None:
        """Apelido atribuído por uma regra de `account_map`, ou `None` se só o padrão vale.

        Diferente de `route`, não cai em `default_account`: diz se a operação foi atribuída a
        uma conta de propósito (usado pelo teste de acesso vertical).
        """
        for rule in self.account_map:
            if rule.covers(operation_id, method, path):
                return rule.account
        return None

    def ensure_operations_exist(self, operation_ids: Sequence[str]) -> None:
        """Garante que toda operação citada em `account_map` existe no OpenAPI.

        Raises:
            ConfigError: `operationId` desconhecido.
        """
        known = set(operation_ids)
        for rule in self.account_map:
            for name in rule.operations:
                if name not in known:
                    raise ConfigError(
                        f"auth.account_map cita a operação {safe_identifier(name)}, "
                        "que não existe no OpenAPI.",
                        hint="Corrija operations em auth.account_map (veja spec inspect).",
                    )
