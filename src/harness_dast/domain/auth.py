"""Autenticação do perfil: exatamente os dois tipos da V1 (decisão P-04).

- `login_password`: usuário e senha enviados a um endpoint de login que devolve um token.
  Não é OAuth2 (não há fluxo de autorização nem client credentials).
- `api_key`: chave fixa enviada num cabeçalho.

Os demais tipos (client credentials, formulário, SSO) ficam para depois e são recusados.
Toda credencial é um `SecretRef`.
"""

import re
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from harness_dast.domain.pathpattern import parse_pattern
from harness_dast.domain.secret_ref import ProfileModel, SecretRef

_ALIAS = re.compile(r"[a-z][a-z0-9_]{0,31}")
_HEADER = re.compile(r"[A-Za-z0-9-]{1,64}")
_FIELD_NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_RESPONSE_PATH = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*")
_SCHEME = re.compile(r"[A-Za-z0-9._~+/-]{0,32}")
# Cabeçalhos que o cliente HTTP controla; permitir que o perfil os defina abriria a porta
# para desvio de roteamento (Host) e contrabando de requisição.
_RESERVED_HEADERS = frozenset({"host", "content-length", "transfer-encoding", "connection"})
_MAX_ACCOUNTS = 20


class Account(ProfileModel):
    """Conta de teste, identificada por um apelido que é o único nome visto pelo agente.

    Attributes:
        alias: Apelido único (`user_a`): minúsculas, dígitos e `_`.
        role: Papel da conta no produto (ex.: `paciente`), texto livre curto.
    """

    alias: str
    role: str = Field(min_length=1, max_length=64)

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, value: str) -> str:
        """Aceita só apelidos simples, que nunca se parecem com um segredo."""
        if not _ALIAS.fullmatch(value):
            raise ValueError("alias inválido; use minúsculas, dígitos e '_' (ex.: user_a)")
        return value

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        """Recusa papel em branco ou com caractere não imprimível."""
        if not value.strip() or not value.isprintable():
            raise ValueError("papel vazio ou com caractere não imprimível")
        return value


class LoginAccount(Account):
    """Conta que faz login com usuário e senha.

    Attributes:
        username: Referência do usuário.
        password: Referência da senha.
    """

    username: SecretRef
    password: SecretRef


class ApiKeyAccount(Account):
    """Conta autenticada por chave fixa.

    Attributes:
        api_key: Referência da chave.
    """

    api_key: SecretRef


def _ensure_unique_aliases(accounts: tuple[Account, ...]) -> None:
    aliases = [account.alias for account in accounts]
    if len(set(aliases)) != len(aliases):
        raise ValueError("apelidos de conta (alias) repetidos; cada conta precisa de um único")


def _validated_header(value: str) -> str:
    if not _HEADER.fullmatch(value) or value.lower() in _RESERVED_HEADERS:
        raise ValueError("nome de cabeçalho inválido ou reservado ao cliente HTTP")
    return value


class PasswordLoginAuth(ProfileModel):
    """Login em endpoint que recebe usuário e senha e devolve um token.

    Attributes:
        type: Sempre `login_password`.
        token_path: Caminho do endpoint de login (literal, sem curingas). Precisa estar
            coberto por `scope.allow` com o método POST.
        accounts: Contas de teste, ao menos uma, com apelidos únicos.
        request_encoding: Como enviar credenciais: `form` (padrão OAuth2) ou `json`.
        username_field: Nome do campo do usuário no corpo do login.
        password_field: Nome do campo da senha no corpo do login.
        token_response_field: Onde está o token na resposta JSON, em caminho pontuado
            (`access_token` ou `data.token`).
        token_header: Cabeçalho em que o token é enviado nas requisições.
        token_scheme: Prefixo do valor do cabeçalho (`Bearer`); vazio envia só o token.
    """

    type: Literal["login_password"]
    token_path: str
    accounts: tuple[LoginAccount, ...] = Field(min_length=1, max_length=_MAX_ACCOUNTS)
    request_encoding: Literal["form", "json"] = "form"
    username_field: str = "username"
    password_field: str = "password"  # noqa: S105 - nome do campo no corpo, não um segredo
    token_response_field: str = "access_token"  # noqa: S105 - nome do campo, não um segredo
    token_header: str = "Authorization"  # noqa: S105 - nome de cabeçalho, não um segredo
    token_scheme: str = "Bearer"  # noqa: S105 - esquema do cabeçalho, não um segredo

    @field_validator("token_path")
    @classmethod
    def validate_token_path(cls, value: str) -> str:
        """Exige caminho literal começando com '/', sem curingas."""
        parse_pattern(value)
        if "*" in value:
            raise ValueError("token_path deve ser um caminho literal, sem curingas")
        return value

    @field_validator("username_field", "password_field")
    @classmethod
    def validate_field_names(cls, value: str) -> str:
        """Confere o nome do campo do corpo."""
        if not _FIELD_NAME.fullmatch(value):
            raise ValueError("nome de campo inválido")
        return value

    @field_validator("token_response_field")
    @classmethod
    def validate_response_field(cls, value: str) -> str:
        """Confere o caminho pontuado do token na resposta."""
        if not _RESPONSE_PATH.fullmatch(value):
            raise ValueError("caminho do token na resposta inválido (ex.: access_token)")
        return value

    @field_validator("token_header")
    @classmethod
    def validate_token_header(cls, value: str) -> str:
        """Confere o nome do cabeçalho."""
        return _validated_header(value)

    @field_validator("token_scheme")
    @classmethod
    def validate_token_scheme(cls, value: str) -> str:
        """Confere o prefixo do cabeçalho (sem espaços nem controle)."""
        if not _SCHEME.fullmatch(value):
            raise ValueError("esquema do token inválido (ex.: Bearer)")
        return value

    @model_validator(mode="after")
    def validate_accounts(self) -> Self:
        """Garante apelidos únicos."""
        _ensure_unique_aliases(self.accounts)
        return self


class ApiKeyAuth(ProfileModel):
    """Chave fixa de API enviada num cabeçalho com nome definido.

    Attributes:
        type: Sempre `api_key`.
        header_name: Cabeçalho que leva a chave (ex.: `X-API-Key`).
        accounts: Contas de teste, ao menos uma, com apelidos únicos.
    """

    type: Literal["api_key"]
    header_name: str
    accounts: tuple[ApiKeyAccount, ...] = Field(min_length=1, max_length=_MAX_ACCOUNTS)

    @field_validator("header_name")
    @classmethod
    def validate_header_name(cls, value: str) -> str:
        """Confere o nome do cabeçalho."""
        return _validated_header(value)

    @model_validator(mode="after")
    def validate_accounts(self) -> Self:
        """Garante apelidos únicos."""
        _ensure_unique_aliases(self.accounts)
        return self


type AuthConfig = Annotated[PasswordLoginAuth | ApiKeyAuth, Field(discriminator="type")]
