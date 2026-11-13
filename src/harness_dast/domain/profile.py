"""Perfil de produto (`target.yml`) como modelo validado e imutável.

O perfil chega aqui já como dados Python (dict); ler o YAML é tarefa de um adaptador. A
entrada principal é `ProductProfile.from_data`, que converte qualquer problema em
`ConfigError` com uma lista legível por campo e sem repetir valores recebidos (um segredo
digitado no lugar errado nunca aparece na mensagem).

Mudar o formato do perfil muda o contrato público: exige subir `schema_version` e um ADR.
"""

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Literal, Self

from pydantic import Field, StrictBool, ValidationError, field_validator, model_validator

from harness_dast.domain.auth import AuthConfig, PasswordLoginAuth
from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.profile_errors import to_config_error
from harness_dast.domain.run import SLUG_PATTERN, RunLimits
from harness_dast.domain.scope import OutboundRequest, Scope, ScopeGuard
from harness_dast.domain.secret_ref import ProfileModel, SecretRef
from harness_dast.domain.urlnorm import normalize_request
from harness_dast.domain.window import (
    Authorization,
    ExecutionWindow,
    ensure_any_window_open,
)

SUPPORTED_SCHEMA_VERSION = 1
_ENV_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
_PRODUCT = re.compile(SLUG_PATTERN)
_PROFILE_HINT = "Corrija os campos indicados no perfil do produto (target.yml)."


def _validate_relative_path(value: str) -> str:
    """Aceita só caminho relativo, dentro da pasta do produto (sem I/O)."""
    parts = value.replace("\\", "/").split("/") if value else []
    invalid = (
        not value
        or len(value) > 260
        or "\\" in value
        or ":" in value
        or value.startswith(("/", "~"))
        or ".." in parts
        or not value.isprintable()
    )
    if invalid:
        raise ValueError(
            "caminho deve ser relativo à pasta do produto, sem '..', '~', unidade (C:), "
            "barra invertida nem caractere de controle"
        )
    return value


class Environment(ProfileModel):
    """Ambiente alvo.

    Attributes:
        name: Nome curto do ambiente (ex.: `homolog`).
        base_url: URL base http(s), sem consulta nem fragmento; sua origem precisa ser
            coberta por `scope.allow`.
    """

    name: str
    base_url: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Aceita nomes curtos em minúsculas."""
        if not _ENV_NAME.fullmatch(value):
            raise ValueError("nome de ambiente inválido; use minúsculas, dígitos, '-' e '_'")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        """Exige URL http(s) bem formada, sem consulta nem fragmento."""
        if "?" in value or "#" in value:
            raise ValueError("base_url não pode ter consulta nem fragmento")
        try:
            normalize_request("GET", value)
        except ScopeViolation as error:
            raise ValueError(f"base_url inválida: {error.message}") from None
        return value


class ProfileScope(Scope):
    """Seção `scope` do perfil: o escopo de rede mais autorização e janelas.

    Attributes:
        authorization: Referência e validade da autorização formal.
        windows: Janelas de execução (forma compacta no YAML); ao menos uma. A execução é
            permitida quando QUALQUER uma está aberta.
    """

    authorization: Authorization
    windows: tuple[ExecutionWindow, ...] = Field(min_length=1, max_length=20)

    @field_validator("windows", mode="before")
    @classmethod
    def parse_windows(cls, value: object) -> object:
        """Converte a forma compacta (texto) em `ExecutionWindow`."""
        if not isinstance(value, list | tuple):
            return value
        parsed: list[object] = []
        for item in value:
            if isinstance(item, str):
                try:
                    parsed.append(ExecutionWindow.parse(item))
                except ConfigError as error:
                    raise ValueError(f"{error.message} {error.hint or ''}".strip()) from None
            else:
                parsed.append(item)
        return parsed

    def to_scope(self) -> Scope:
        """Devolve só a parte de rede (regras e negações), sem autorização nem janelas."""
        return Scope(allow=self.allow, deny_paths=self.deny_paths)


class CleanupConfig(ProfileModel):
    """Hook de limpeza do ambiente (AD-13): SQL escrito por pessoa, executado com confirmação.

    Attributes:
        type: Somente `oracle_sql` na V1.
        script: Caminho relativo do script SQL, escrito e revisado por uma pessoa.
        connection: Referência da conexão (usuário de banco restrito às tabelas de teste).
        requires_confirmation: Deve ser `true`. Na V1 a confirmação humana não é opcional.
    """

    type: Literal["oracle_sql"]
    script: str
    connection: SecretRef
    requires_confirmation: StrictBool

    @field_validator("script")
    @classmethod
    def validate_script(cls, value: str) -> str:
        """Exige caminho relativo seguro."""
        return _validate_relative_path(value)

    @field_validator("requires_confirmation")
    @classmethod
    def validate_confirmation(cls, value: bool) -> bool:
        """Recusa `false`: a limpeza sempre exige confirmação humana na V1."""
        if value is not True:
            raise ValueError(
                "requires_confirmation deve ser true; a confirmação é obrigatória na V1"
            )
        return value


class ProductProfile(ProfileModel):
    """Perfil completo de um produto, imutável e já validado.

    Attributes:
        schema_version: Sempre 1.
        product: Slug do produto.
        environment: Ambiente alvo.
        openapi: Caminho relativo do OpenAPI (a leitura do arquivo não é feita aqui).
        scope: Escopo de rede, autorização e janelas.
        limits: Limites de carga.
        auth: Autenticação (um dos dois tipos da V1).
        cleanup: Limpeza, opcional.
    """

    schema_version: Literal[1]
    product: str
    environment: Environment
    openapi: str
    scope: ProfileScope
    limits: RunLimits
    auth: AuthConfig
    cleanup: CleanupConfig | None = None

    @field_validator("product")
    @classmethod
    def validate_product(cls, value: str) -> str:
        """Exige slug em minúsculas."""
        if not _PRODUCT.fullmatch(value):
            raise ValueError("product inválido; use slug em minúsculas, dígitos e '-'")
        return value

    @field_validator("openapi")
    @classmethod
    def validate_openapi(cls, value: str) -> str:
        """Exige caminho relativo seguro."""
        return _validate_relative_path(value)

    @model_validator(mode="after")
    def validate_consistency(self) -> Self:
        """Confere que o ambiente e o login estão dentro do escopo declarado."""
        guard = self.guard()
        try:
            guard.ensure_origin_allowed(self.environment.base_url)
        except ScopeViolation:
            raise ValueError(
                "o host de environment.base_url não é coberto por scope.allow; "
                "inclua uma regra para ele (host, esquema e porta)"
            ) from None
        if isinstance(self.auth, PasswordLoginAuth):
            login = self.environment.base_url.rstrip("/") + self.auth.token_path
            try:
                guard.ensure_allowed(OutboundRequest(method="POST", url=login))
            except ScopeViolation as error:
                raise ValueError(
                    f"o login (POST em auth.token_path) está fora do escopo: {error.message}"
                ) from None
        return self

    @classmethod
    def from_data(cls, data: object) -> Self:
        """Constrói o perfil a partir de dados já lidos do YAML.

        Raises:
            ConfigError: Para qualquer problema: `schema_version` ausente ou diferente de 1,
                campo faltando, desconhecido ou inválido, segredo literal, base_url fora
                do escopo etc. A mensagem lista cada problema por caminho do campo, em
                português, e nunca contém os valores informados.
        """
        _ensure_supported_version(data)
        try:
            return cls.model_validate(data)
        except ValidationError as error:
            raise to_config_error(error, hint=_PROFILE_HINT) from None

    def guard(self) -> ScopeGuard:
        """Cria o `ScopeGuard` deste perfil."""
        return ScopeGuard(self.scope.to_scope())

    def ensure_runnable(self, now: datetime) -> None:
        """Garante autorização válida e janela aberta em `now`.

        Raises:
            ScopeViolation: Autorização expirada ou nenhuma janela aberta.
            ConfigError: `now` sem fuso.
        """
        self.scope.authorization.ensure_valid(now)
        ensure_any_window_open(self.scope.windows, now)


def _ensure_supported_version(data: object) -> None:
    if not isinstance(data, Mapping):
        raise ConfigError("O perfil deve ser um mapa de campos.", hint=_PROFILE_HINT)
    if "schema_version" not in data:
        raise ConfigError(
            "O perfil não informa schema_version.",
            hint=f"Adicione schema_version: {SUPPORTED_SCHEMA_VERSION}.",
        )
    version = data["schema_version"]
    if type(version) is not int or version != SUPPORTED_SCHEMA_VERSION:
        shown = f" {version}" if type(version) is int else ""
        raise ConfigError(
            f"schema_version{shown} não é suportada; esta versão aceita apenas "
            f"{SUPPORTED_SCHEMA_VERSION}.",
            hint="Atualize o perfil para o schema atual ou use a versão da CLI correspondente.",
        )
