"""Carta de autorização estruturada (`carta.yml`): o formulário que a pessoa responde (ADR 0036).

O agente transcreve as respostas da pessoa neste arquivo de formato fechado; a CLI gera os
blocos de proteção do `target.yml` a partir dele (`letter_review`). Nada aqui decide escopo:
este módulo só descreve a forma e recusa campo desconhecido, tipo errado e origem inválida.

Cada resposta é um `Answer`: valor, origem (`carta`, `pessoa` ou `desconhecido`) e,
opcionalmente, a frase de origem. O formato cresce por adição: um campo novo é um `Answer`
opcional numa seção; `schema_version` só sobe numa mudança incompatível.
"""

import re
from collections.abc import Mapping
from typing import Final, Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile_errors import to_config_error
from harness_dast.domain.run import SLUG_PATTERN
from harness_dast.domain.secret_ref import ProfileModel

SUPPORTED_LETTER_VERSION: Final = 1
LETTER_HINT: Final = (
    "Corrija os campos indicados no carta.yml. Cada resposta tem a forma "
    "{value: ..., source: carta|pessoa|desconhecido}; quem responde é a pessoa, não o agente."
)
Source = Literal["carta", "pessoa", "desconhecido"]
MAX_QUOTE_CHARS: Final = 300
_PRODUCT = re.compile(SLUG_PATTERN)


class Answer(ProfileModel):
    """Uma resposta do formulário.

    Attributes:
        value: O valor respondido (o tipo esperado depende do campo; quem confere é
            `letter_review`). Ausente ou nulo conta como "sem resposta".
        source: De onde veio: `carta` (a carta assinada diz isso), `pessoa` (a pessoa
            respondeu na entrevista) ou `desconhecido` ("não sei" / "não está na carta"; sem
            valor). Resposta desconhecida em campo obrigatório recusa a carta.
        quote: Frase da carta ou da conversa que sustenta a resposta (opcional; obrigatória
            para `path_mode: wide`).
    """

    value: object = None
    source: Source
    quote: str | None = Field(default=None, max_length=MAX_QUOTE_CHARS)

    @field_validator("quote")
    @classmethod
    def validate_quote(cls, value: str | None) -> str | None:
        """Recusa frase com caractere de controle."""
        if value is not None and not value.isprintable():
            raise ValueError("a frase de origem tem caractere não imprimível")
        return value

    @model_validator(mode="after")
    def validate_unknown_has_no_value(self) -> Self:
        """Uma resposta `desconhecido` não traz valor (não há o que transcrever)."""
        if self.source == "desconhecido" and self.value is not None:
            raise ValueError("uma resposta desconhecida não pode ter value; apague o valor")
        return self


class Gates(ProfileModel):
    """Portões: sem os quatro respondidos "sim" (ou com o dono do produto), nada é gerado.

    Attributes:
        test_environment: O ambiente é de teste (não é produção)? `true`.
        synthetic_data: Os dados são sintéticos (sem pessoas reais)? `true`.
        authorization_in_force: Existe autorização vigente do dono do produto? `true`.
        product_owner: Nome (e contato) do dono do produto que autorizou.
    """

    test_environment: Answer | None = None
    synthetic_data: Answer | None = None
    authorization_in_force: Answer | None = None
    product_owner: Answer | None = None


class EnvironmentSection(ProfileModel):
    """Endereço do ambiente de teste.

    Attributes:
        name: Nome curto do ambiente (`homolog`, `lab`) -> `environment.name`.
        base_url: URL base http(s) -> `environment.base_url`.
        openapi: Caminho do OpenAPI relativo à pasta do produto -> `openapi`.
    """

    name: Answer | None = None
    base_url: Answer | None = None
    openapi: Answer | None = None


class ScopeSection(ProfileModel):
    """Onde e como o teste pode tocar o alvo.

    Attributes:
        allow: Lista de regras `{host, scheme, port?, allow_local?, paths, methods}`, uma por
            host autorizado -> `scope.allow`.
        deny_paths: Caminhos proibidos (lista; vazia só se a pessoa disser que não há)
            -> `scope.deny_paths`.
        path_mode: `strict` (padrão, vale se ausente) ou `wide` (só com origem `carta` e
            frase de origem) -> `scope.path_mode`.
    """

    allow: Answer | None = None
    deny_paths: Answer | None = None
    path_mode: Answer | None = None


class AuthorizationSection(ProfileModel):
    """Autorização formal e janelas.

    Attributes:
        reference: Referência da autorização (ticket, e-mail) -> `scope.authorization.reference`.
        valid_until: Último dia de validade (AAAA-MM-DD) -> `scope.authorization.valid_until`.
        windows: Janelas no formato compacto (`seg-sex 20:00-06:00 America/Sao_Paulo`)
            -> `scope.windows`.
    """

    reference: Answer | None = None
    valid_until: Answer | None = None
    windows: Answer | None = None


class LimitsSection(ProfileModel):
    """Limites de carga -> `limits`.

    Attributes:
        requests_per_second: Teto de requisições por segundo.
        max_duration_minutes: Duração máxima de uma execução, em minutos.
        zap_threads_per_host: Conexões simultâneas do varredor por host.
    """

    requests_per_second: Answer | None = None
    max_duration_minutes: Answer | None = None
    zap_threads_per_host: Answer | None = None


class AuthSection(ProfileModel):
    """Como entrar e com quais contas (só NOMES de segredo, nunca o valor).

    Attributes:
        type: `login_password` ou `api_key` -> `auth.type`.
        token_path: Caminho do login (só `login_password`) -> `auth.token_path`.
        header_name: Cabeçalho da chave (só `api_key`) -> `auth.header_name`.
        login_options: Mapa opcional com `request_encoding`, `username_field`,
            `password_field`, `token_response_field`, `token_header`, `token_scheme`
            (só `login_password`); ausente mantém os padrões do perfil.
        login_max_per_minute: Logins por minuto que o alvo tolera -> `auth.login_limit`.
        accounts: Contas `{alias, role, username/password ou api_key: {secret_ref: env:NOME}}`
            -> `auth.accounts`.
    """

    type: Answer | None = None
    token_path: Answer | None = None
    header_name: Answer | None = None
    login_options: Answer | None = None
    login_max_per_minute: Answer | None = None
    accounts: Answer | None = None


class AttackSection(ProfileModel):
    """Intensidade do ataque e permissão de escrita do teste entre contas (opcionais).

    Attributes:
        strength: `LOW`, `MEDIUM` ou `HIGH` -> `scan.strength`. Ausente mantém o padrão do
            perfil (a CLI não decide por conta própria).
        allow_authz_writes: A carta permite que o teste de autorização entre contas ESCREVA no
            alvo (atribuição em massa, alteração de recurso de outra conta e métodos de escrita da
            verificação vertical e da tabela quem pode o quê)? Booleano
            -> `authz.allow_writes`. Ausente, nulo ou `desconhecido` valem `false`; `true` só
            com `source: carta` e a frase de origem em `quote` (ADR 0038).
    """

    strength: Answer | None = None
    allow_authz_writes: Answer | None = None


class Letter(ProfileModel):
    """A carta estruturada inteira, na ordem da entrevista.

    Attributes:
        schema_version: Sempre 1.
        product: Slug do produto; precisa ser igual ao argumento de `hdast init`.
        gates: Portões.
        environment: Endereço do ambiente.
        scope: Escopo.
        authorization: Autorização e janelas.
        limits: Limites.
        auth: Autenticação e contas.
        attack: Intensidade do ataque.
        example_data: Dados de exemplo que existem no ambiente (lista de
            `{operation?, field, value, note?}`). Informação para o agente escrever o
            `data-rules.yml`; a CLI não os transforma em regra.
    """

    schema_version: Literal[1]
    product: str
    gates: Gates = Gates()
    environment: EnvironmentSection = EnvironmentSection()
    scope: ScopeSection = ScopeSection()
    authorization: AuthorizationSection = AuthorizationSection()
    limits: LimitsSection = LimitsSection()
    auth: AuthSection = AuthSection()
    attack: AttackSection = AttackSection()
    example_data: Answer | None = None

    @field_validator("product")
    @classmethod
    def validate_product(cls, value: str) -> str:
        """Exige slug em minúsculas, igual ao do perfil."""
        if not _PRODUCT.fullmatch(value):
            raise ValueError("product inválido; use slug em minúsculas, dígitos e '-'")
        return value

    @classmethod
    def from_data(cls, data: object) -> Self:
        """Constrói a carta a partir do mapa lido do YAML.

        Raises:
            ConfigError: `schema_version` ausente ou diferente de 1, campo desconhecido,
                resposta fora do formato `{value, source}` etc. A mensagem lista cada
                problema por caminho e nunca contém os valores informados.
        """
        _ensure_supported_version(data)
        try:
            return cls.model_validate(data)
        except ValidationError as error:
            raise to_config_error(error, hint=LETTER_HINT, subject="Carta", feminine=True) from None


def _ensure_supported_version(data: object) -> None:
    if not isinstance(data, Mapping):
        raise ConfigError("A carta deve ser um mapa de campos.", hint=LETTER_HINT)
    version = data.get("schema_version")
    if type(version) is not int or version != SUPPORTED_LETTER_VERSION:
        raise ConfigError(
            "A carta não informa schema_version: 1 (ou usa outra versão).",
            hint=f"Adicione schema_version: {SUPPORTED_LETTER_VERSION} no início do carta.yml.",
        )
