"""Conhecimento versionado, sem valores de resposta ou autoridade própria."""

from datetime import UTC, date, datetime
from typing import Literal, Self

from pydantic import Field, ValidationError, field_validator

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge_receipts import KnowledgeFlowUse, KnowledgeRuleUse
from harness_dast.domain.secret_ref import ProfileModel
from harness_dast.domain.strategy import StrategyReferences
from harness_dast.domain.strategy_basis import StrategyBasis, StrategyBasisContext
from harness_dast.domain.window import ensure_aware

Dependency = Literal[
    "environment",
    "authorization",
    "accounts",
    "planning",
    "openapi",
    "data_rules",
    "flows",
    "engine",
]
Kind = Literal["account", "data", "flow", "effect", "authentication"]

# Toda entrada depende do envelope; as demais fontes são específicas por categoria.
_REQUIRED: dict[str, frozenset[str]] = {
    "account": frozenset({"environment", "authorization", "accounts"}),
    "data": frozenset({"environment", "authorization", "openapi", "data_rules"}),
    "flow": frozenset({"environment", "authorization", "openapi", "flows"}),
    "effect": frozenset({"environment", "authorization", "accounts", "openapi", "flows"}),
    "authentication": frozenset({"environment", "authorization", "accounts"}),
}


class KnowledgeProvenance(ProfileModel):
    """Resumos das fontes da captura; nao autenticam a autoria dos arquivos."""

    run_id: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    probe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authz_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        """Rejeita identificador fora do formato do produto."""
        from harness_dast.domain.run_ref import require_run_id

        return require_run_id(value)


class KnowledgeEffect(ProfileModel):
    """Receita sanitizada de efeito comprovado por releitura, sem valor ou ID."""

    write_operation: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.-]{0,199}$")
    read_operation: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.-]{0,199}$")
    account: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    fields: tuple[str, ...] = Field(min_length=1, max_length=50)
    proof: Literal["readback_verified"]

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Aceita apenas nomes estruturais curtos e distintos."""
        import re

        if len(set(value)) != len(value) or any(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,99}", name) is None for name in value
        ):
            raise ValueError("campos invalidos")
        return value


class KnowledgeEntry(ProfileModel):
    """Declaração fechada e rastreável, sem conteúdo textual arbitrário."""

    kind: Kind
    source: Literal["owner", "contract", "observation"]
    reason: Literal["references_existing_documents"]
    state: Literal["proposed", "validated", "review_required"]
    valid_until: date
    dependencies: tuple[Dependency, ...] = Field(min_length=1, max_length=8)

    @field_validator("valid_until", mode="before")
    @classmethod
    def validate_date(cls, value: object) -> object:
        """Aceita somente data ISO explícita."""
        if type(value) is date:
            return value
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("data inválida")
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError("data inválida") from None
        if parsed.isoformat() != value:
            raise ValueError("data inválida")
        return parsed

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, value: tuple[Dependency, ...]) -> tuple[Dependency, ...]:
        """Recusa duplicatas ambíguas."""
        if len(set(value)) != len(value):
            raise ValueError("dependências duplicadas")
        return value


class Knowledge(ProfileModel):
    """Conhecimento congelado; observação não altera o perfil nem autoriza pedidos."""

    schema_version: Literal[1]
    basis: StrategyBasis
    references: StrategyReferences
    provenance: KnowledgeProvenance | None = None
    observed_accounts: tuple[str, ...] = Field(default=(), max_length=20)
    observed_rules: tuple[KnowledgeRuleUse, ...] = Field(default=(), max_length=5000)
    observed_flows: tuple[KnowledgeFlowUse, ...] = Field(default=(), max_length=5000)
    effects: tuple[KnowledgeEffect, ...] = Field(default=(), max_length=500)
    entries: tuple[KnowledgeEntry, ...] = Field(max_length=1000)

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_version(cls, value: object) -> object:
        """Recusa coerção de booleanos e versões não suportadas."""
        if type(value) is not int or value != 1:
            raise ValueError("versão inválida")
        return value

    @classmethod
    def from_data(cls, data: object) -> Self:
        """Valida entrada externa sem ecoar dados recebidos."""
        try:
            knowledge = cls.model_validate(data)
        except ValidationError:
            raise ConfigError("Conhecimento inválido.", hint="Corrija knowledge.yml.") from None
        if any(
            not _REQUIRED[entry.kind].issubset(entry.dependencies) for entry in knowledge.entries
        ):
            raise ConfigError("Dependências incompletas em knowledge.yml.")
        if {entry.kind for entry in knowledge.entries} != set(_REQUIRED) or len(
            knowledge.entries
        ) != len(_REQUIRED):
            raise ConfigError("Categorias incompletas ou duplicadas em knowledge.yml.")
        if any(
            not {"engine", "planning"}.issubset(entry.dependencies) for entry in knowledge.entries
        ):
            raise ConfigError("Vinculo com motor ou planejamento ausente em knowledge.yml.")
        if (
            knowledge.observed_accounts
            or knowledge.observed_rules
            or knowledge.observed_flows
            or knowledge.effects
        ) and knowledge.provenance is None:
            raise ConfigError("Observacoes sem proveniencia.")
        if knowledge.effects and (
            knowledge.provenance is None or knowledge.provenance.authz_sha256 is None
        ):
            raise ConfigError("Efeitos sem evidencia de autorizacao.")
        categories = {
            "account": bool(knowledge.observed_accounts),
            "authentication": bool(knowledge.observed_accounts),
            "data": bool(knowledge.observed_rules),
            "flow": bool(knowledge.observed_flows),
            "effect": bool(knowledge.effects),
        }
        if any(
            entry.source == "observation"
            and entry.state == "validated"
            and (knowledge.provenance is None or not categories[entry.kind])
            for entry in knowledge.entries
        ):
            raise ConfigError("Observacao validada sem recibo correspondente.")
        return knowledge

    def review(self, current: StrategyBasisContext, now: datetime) -> tuple[tuple[str, ...], ...]:
        """Devolve motivos por entrada; motor ausente invalida entradas que dependem dele."""
        ensure_aware(now)
        old = self.basis.model_dump()
        new = current.model_dump()
        results = []
        for entry in self.entries:
            reasons: list[str] = [name for name in entry.dependencies if old[name] != new[name]]
            if entry.state != "validated":
                reasons.append("state")
            if entry.valid_until < now.astimezone(UTC).date():
                reasons.append("expired")
            results.append(tuple(reasons))
        return tuple(results)
