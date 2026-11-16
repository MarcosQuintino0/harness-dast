"""Revalidação do conhecimento ativo antes de carregar documentos reutilizados."""

from harness_dast.application.ports import (
    Clock,
    KnowledgeStore,
    ProfileRepository,
    ReferencedFile,
    StrategyDependencyStore,
    ZapControl,
)
from harness_dast.application.strategy import basis_for_engine, describe_current_basis
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.knowledge import Knowledge, KnowledgeEffect
from harness_dast.domain.knowledge_checks import ensure_flow_use, ensure_rule_use
from harness_dast.domain.knowledge_receipts import KnowledgeRuleUse
from harness_dast.domain.profile import ProductProfile


class KnowledgeProfiles:
    """Exige fontes e motor atuais para conhecimento ativo; nunca concede permissão."""

    def __init__(
        self,
        inner: ProfileRepository,
        store: KnowledgeStore,
        dependencies: StrategyDependencyStore,
        clock: Clock,
        zap: ZapControl | None,
    ) -> None:
        """Recebe perfil já verificado e fontes independentes."""
        self._inner, self._store, self._deps, self._clock, self._zap = (
            inner,
            store,
            dependencies,
            clock,
            zap,
        )

    def load(self, product: str) -> ProductProfile:
        """Recusa conhecimento inválido, pendente, expirado ou desvinculado."""
        profile = self._inner.load(product)
        raw = self._store.read(product)
        if raw is None:
            return profile
        knowledge = Knowledge.from_data(raw)
        if not any(e.kind != "effect" and e.state == "validated" for e in knowledge.entries):
            return profile  # só proposta: nada é consumido, então nada depende do motor
        self._deps.check_references(product, knowledge.references)
        if self._zap is None:
            raise ConfigError(
                "Conhecimento validado exige o motor atual, que esta consulta não abre.",
                hint="Rode o comando ativo, ou rebaixe a entrada para proposta em knowledge.yml.",
            )
        basis = basis_for_engine(self._deps, product, profile, self._zap.version())
        if basis is None:
            raise ConfigError("Motor indisponível para validar conhecimento.")
        checks = knowledge.review(basis, self._clock.now())
        if any(
            reasons
            for entry, reasons in zip(knowledge.entries, checks, strict=True)
            if entry.kind != "effect" and entry.state == "validated"
        ):
            raise ConfigError(
                "Conhecimento vencido ou fontes alteradas; revise antes de reutilizar."
            )
        return profile

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Mantém a verificação de arquivos do repositório subjacente."""
        return self._inner.missing_files(product, profile)


class InspectKnowledge:
    """Consulta conhecimento e diferenças locais sem acessar motor ou alvo."""

    def __init__(
        self,
        profiles: ProfileRepository,
        store: KnowledgeStore,
        dependencies: StrategyDependencyStore,
        clock: Clock,
    ) -> None:
        """Recebe fontes independentes e relógio injetado."""
        self._profiles, self._store, self._deps, self._clock = profiles, store, dependencies, clock

    def inspect(self, product: str) -> dict[str, JsonValue]:
        """Classifica cada referência sem considerar motor indisponível como válido."""
        profile = self._profiles.load(product)
        raw = self._store.read(product)
        if raw is None:
            raise ConfigError("knowledge.yml ausente.")
        knowledge = Knowledge.from_data(raw)
        self._deps.check_references(product, knowledge.references)
        current = describe_current_basis(self._deps, product, profile)
        reasons = knowledge.review(current, self._clock.now())
        return {
            "product": product,
            "entries": [
                {"kind": entry.kind, "reasons": list(reason)}
                for entry, reason in zip(knowledge.entries, reasons, strict=True)
            ],
            "reusable": _reusable(knowledge, reasons),
            "classification": "proposed" if any(reasons) else "automatic",
            "engine_status": "unavailable",
        }


def _reusable(knowledge: Knowledge, reasons: tuple[tuple[str, ...], ...]) -> bool:
    """Há entrada validada consumível e nenhuma delas tem motivo de invalidação."""
    validated = [
        reason
        for entry, reason in zip(knowledge.entries, reasons, strict=True)
        if entry.kind != "effect" and entry.state == "validated"
    ]
    return bool(validated) and not any(validated)


def load_validated_effects(
    product: str,
    profile: ProductProfile,
    store: KnowledgeStore,
    dependencies: StrategyDependencyStore,
    clock: Clock,
    zap: ZapControl | None,
) -> tuple[KnowledgeEffect, ...]:
    """Entrega receitas atuais ou vazio; nunca amplia trabalho ou autorizacao."""
    if profile.product != product:
        raise ConfigError("Produto divergente na verificacao do conhecimento.")
    raw = store.read(product)
    if raw is None:
        return ()
    knowledge = Knowledge.from_data(raw)
    dependencies.check_references(product, knowledge.references)
    effect = next(entry for entry in knowledge.entries if entry.kind == "effect")
    if effect.state != "validated" or effect.source != "observation" or not knowledge.effects:
        return ()
    if zap is None:
        return ()
    basis = basis_for_engine(dependencies, product, profile, zap.version())
    if basis is None:
        return ()
    checks = knowledge.review(basis, clock.now())
    for entry, reasons in zip(knowledge.entries, checks, strict=True):
        if entry.kind == "effect":
            return () if reasons else knowledge.effects
    return ()


class ExecutableKnowledge:
    """Confere receitas observadas sem substituir documentos ou diminuir cobertura."""

    def __init__(
        self,
        store: KnowledgeStore,
        dependencies: StrategyDependencyStore,
        clock: Clock,
        zap: ZapControl | None,
    ) -> None:
        """Recebe fontes independentes e motor atual."""
        self._store, self._deps, self._clock, self._zap = store, dependencies, clock, zap

    def validate(
        self,
        product: str,
        profile: ProductProfile,
        spec: ApiSpec,
        rules: DataRules,
        flows: FlowSpec | None,
    ) -> tuple[KnowledgeRuleUse, ...]:
        """Confere referências comprovadas e mantém fallback para entradas propostas."""
        raw = self._store.read(product)
        if raw is None or self._zap is None:
            return ()
        knowledge = Knowledge.from_data(raw)
        self._deps.check_references(product, knowledge.references)
        basis = basis_for_engine(self._deps, product, profile, self._zap.version())
        if basis is None:
            return ()
        valid = {
            entry.kind
            for entry, reasons in zip(
                knowledge.entries, knowledge.review(basis, self._clock.now()), strict=True
            )
            if entry.source == "observation" and entry.state == "validated" and not reasons
        }
        if "account" in valid or "authentication" in valid:
            for alias in knowledge.observed_accounts:
                profile.select_account(alias)
        if "data" in valid:
            for use in knowledge.observed_rules:
                ensure_rule_use(use, rules, spec)
        if "flow" in valid:
            for flow_use in knowledge.observed_flows:
                ensure_flow_use(flow_use, flows, spec)
        return knowledge.observed_rules if "data" in valid else ()
