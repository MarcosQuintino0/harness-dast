"""Política de uma execução do proxy de escopo: leitura e validação do arquivo JSON.

O arquivo é gerado pela CLI a partir do perfil do produto (fora deste módulo) e montado
somente leitura no contêiner. O que garante: ou devolve uma `ProxyPolicy` válida, ou levanta
`ConfigError`; nunca há política padrão que permita algo. O que não faz: não gera o arquivo
nem o recarrega (a política vale até o proxy reiniciar).
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.proxy_deadline import STACK_MARGIN_MINUTES
from harness_dast.domain.run import MAX_DURATION_MINUTES, SLUG_PATTERN, RunId, RunLimits
from harness_dast.domain.scope import PathMode, Scope
from harness_dast.domain.window import Authorization, ExecutionWindow

SCHEMA_VERSION = 1
"""Versão do schema do arquivo; mudar o formato exige novo número e ADR."""

KILL_FLAG_NAME = "KILL"
"""Nome do arquivo-sinal da trava de emergência, no mesmo diretório da política."""

MAX_POLICY_BYTES = 1_048_576
_HINT = "Gere o arquivo de política a partir do perfil (ver docker/scope-proxy/README.md)."


class ApprovalBinding(BaseModel):
    """Fontes locais e validade congeladas para uma pilha gerenciada."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    product: str = Field(pattern=rf"^{SLUG_PATTERN}$")
    approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization: Authorization
    windows: tuple[ExecutionWindow, ...] = Field(min_length=1)


class ProxyPolicy(BaseModel):
    """Política validada de uma execução.

    Attributes:
        schema_version: Sempre `SCHEMA_VERSION`; outro valor é recusado.
        run_id: Identificador da execução (formato de `RunId`), gravado em toda linha de auditoria.
        scope: Mesmo formato do `scope` do perfil: regras `allow` e `deny_paths`.
        limits: Limites da execução; o proxy usa `requests_per_second` e `max_duration_minutes`.
        path_mode: Modo de leitura do caminho (`strict` ou `wide`; ADR 0026). Ausente vale
            `strict`. O modo vem do perfil e a CLI nunca o liga por flag.
        not_after: Prazo absoluto, com fuso; depois dele o proxy nega tudo. É a validade da
            pilha (autorização, janela e `stack_minutes`), não o prazo de uma varredura.
        stack_minutes: Validade da pilha em minutos, contada da partida do proxy. Ausente, vale
            `limits.max_duration_minutes` (política escrita à mão mantém a cerca antiga). A CLI
            grava aqui a duração máxima mais a folga do ajuste do `probe`.
        tls_verify_upstream: Verificar o certificado do servidor de destino (padrão `true`).
            `false` só é aceito se TODA regra tiver `allow_local: true` (laboratório).
        max_queued_requests: Tamanho máximo da fila da taxa; além dele o pedido é recusado (429).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    binding: ApprovalBinding | None = None
    schema_version: StrictInt
    run_id: str
    scope: Scope
    limits: RunLimits
    path_mode: PathMode = "strict"
    not_after: AwareDatetime
    stack_minutes: StrictInt | None = Field(
        default=None, ge=1, le=MAX_DURATION_MINUTES + STACK_MARGIN_MINUTES
    )
    tls_verify_upstream: StrictBool = True
    max_queued_requests: StrictInt = Field(default=100, ge=1, le=1000)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        """Aceita somente a versão de schema que este código entende."""
        if value != SCHEMA_VERSION:
            raise ValueError(f"schema_version deve ser {SCHEMA_VERSION}")
        return value

    @field_validator("not_after", mode="before")
    @classmethod
    def validate_not_after_is_text(cls, value: object) -> object:
        """Exige texto ISO 8601: número vira data em silêncio e esconderia um erro de unidade."""
        if not isinstance(value, str):
            # ValueError (não TypeError): só ele vira ValidationError dentro do pydantic.
            raise ValueError(  # noqa: TRY004
                "not_after deve ser texto ISO 8601 com fuso, por exemplo 2026-11-13T23:00:00Z"
            )
        return value

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        """Confere o formato do identificador (ele vira nome de pasta e campo de log)."""
        RunId(value=value)
        return value

    @model_validator(mode="after")
    def validate_tls_relaxation(self) -> Self:
        """Só permite desligar a verificação de TLS quando todos os alvos são locais."""
        if not self.tls_verify_upstream and not all(r.allow_local for r in self.scope.allow):
            raise ValueError(
                "tls_verify_upstream: false só é aceito quando toda regra de scope.allow "
                "tem allow_local: true (laboratório com certificado autoassinado)"
            )
        return self


def load_policy(path: Path) -> ProxyPolicy:
    """Lê e valida o arquivo de política.

    Args:
        path: Caminho do JSON.

    Returns:
        A política validada.

    Raises:
        ConfigError: Se o arquivo faltar, for grande demais, não for UTF-8/JSON válido, tiver
            chave repetida, campo desconhecido, tipo errado ou valor fora dos limites.
    """
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ConfigError(
            f"Não foi possível ler a política do proxy em {path} ({error.strerror}).", hint=_HINT
        ) from None
    if len(raw) > MAX_POLICY_BYTES:
        raise ConfigError(f"A política do proxy passa de {MAX_POLICY_BYTES} bytes.", hint=_HINT)
    return parse_policy(raw)


def parse_policy(raw: bytes) -> ProxyPolicy:
    """Valida o conteúdo bruto de uma política (mesmas garantias de `load_policy`)."""
    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise ConfigError(f"A política do proxy não é JSON válido: {error}.", hint=_HINT) from None
    if not isinstance(data, dict):
        raise ConfigError("A política do proxy deve ser um objeto JSON.", hint=_HINT)
    try:
        return ProxyPolicy.model_validate(data)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '(raiz)'}: {e['msg']}" for e in error.errors()
        )
        raise ConfigError(f"Política do proxy inválida: {problems}.", hint=_HINT) from None


def deadline_of(policy: ProxyPolicy, started_at: datetime) -> datetime:
    """Instante a partir do qual o proxy nega tudo: o menor entre `not_after` e a validade da pilha.

    A validade conta da partida do proxy: `stack_minutes` ou, sem ele, `max_duration_minutes`.
    """
    minutes = policy.stack_minutes or policy.limits.max_duration_minutes
    return min(policy.not_after, started_at + timedelta(minutes=minutes))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    # Chave repetida: o parser comum fica com a última, e um revisor lê a primeira. Recusar
    # evita um arquivo que "parece" restrito e se comporta de outro modo.
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("chave repetida no objeto")
    return dict(pairs)


def _reject_constant(name: str) -> None:
    raise ValueError(f"constante {name} não é aceita")
