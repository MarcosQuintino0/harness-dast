"""Validação e prévia local de estratégia sem abrir transporte ou conceder autorização."""

from harness_dast.application.ports import (
    ApprovalStore,
    Clock,
    ProductDocuments,
    ProfileRepository,
    ReferencedFile,
    SpecLoader,
    StrategyDependencyStore,
    StrategyStore,
    ZapControl,
)
from harness_dast.application.scope_approval import current_check
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.envelope import describe_envelope
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy import Strategy
from harness_dast.domain.strategy_basis import (
    StrategyBasis,
    StrategyBasisContext,
    describe_strategy_basis,
    digest_strategy_document,
    make_strategy_basis,
)
from harness_dast.domain.strategy_preview import preview


def load_strategy(store: StrategyStore, product: str) -> Strategy | None:
    """Lê estratégia opcional e confere suas referências reais."""
    data = store.read(product)
    if data is None:
        return None
    strategy = Strategy.from_data(data)
    store.check_references(product, strategy.references)
    return strategy


def _context(
    store: StrategyDependencyStore,
    product: str,
    profile: ProductProfile,
    engine_version: str | None = None,
) -> tuple[StrategyBasisContext, StrategyBasis | None]:
    contract, data_rules, flows = store.read_dependencies(product, profile)
    inputs = {
        "openapi_sha256": digest_strategy_document(contract),
        "data_rules_sha256": digest_strategy_document(data_rules),
        "flows_sha256": digest_strategy_document(flows),
    }
    return (
        describe_strategy_basis(profile, **inputs, engine_version=engine_version),
        make_strategy_basis(profile, **inputs, engine_version=engine_version),
    )


def describe_current_basis(
    store: StrategyDependencyStore, product: str, profile: ProductProfile
) -> StrategyBasisContext:
    """Resume fontes locais sem fingir que o motor foi consultado."""
    return _context(store, product, profile)[0]


def basis_for_engine(
    store: StrategyDependencyStore, product: str, profile: ProductProfile, version: str
) -> StrategyBasis | None:
    """Calcula vínculo com a versão efetiva obtida na execução atual."""
    return _context(store, product, profile, version)[1]


class StrategyProfiles:
    """Recusa estratégia inválida ou pendente na fronteira de comandos com tráfego."""

    def __init__(
        self,
        inner: ProfileRepository,
        store: StrategyDependencyStore,
        clock: Clock,
        zap: ZapControl | None = None,
    ) -> None:
        """Recebe perfil, armazenamento e relógio."""
        self._inner, self._store, self._clock = inner, store, clock
        self._zap = zap

    def load(self, product: str) -> ProductProfile:
        """Carrega perfil e valida estratégia presente antes de executar."""
        profile = self._inner.load(product)
        strategy = load_strategy(self._store, product)
        if strategy is not None:
            strategy.ensure_metadata_valid(self._clock.now())
            basis = None
            if strategy.choices:
                version = self._zap.version() if self._zap is not None else None
                _, basis = _context(self._store, product, profile, version)
            strategy.ensure_compilable(self._clock.now(), basis)
        return profile

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Lista documentos ausentes do perfil subjacente."""
        return self._inner.missing_files(product, profile)


class StrategyService:
    """Consulta e migra estratégia sem tráfego ou mudança de aprovação."""

    def __init__(
        self,
        profiles: ProfileRepository,
        store: StrategyDependencyStore,
        approvals: ApprovalStore,
        clock: Clock,
        documents: ProductDocuments,
        specs: SpecLoader,
    ) -> None:
        """Recebe as portas necessárias às operações locais."""
        self._profiles, self._store = profiles, store
        self._approvals, self._clock = approvals, clock
        self._documents = documents
        self._specs = specs

    def inspect(self, product: str) -> dict[str, JsonValue]:
        """Descreve estratégia, estado de aprovação e envelope sem exigir aprovação."""
        profile = self._profiles.load(product)
        strategy = load_strategy(self._store, product)
        self._documents.load_data_rules(product)
        self._documents.load_flows(product)
        context = (
            _context(self._store, product, profile)[0] if strategy and strategy.choices else None
        )
        pending = bool(strategy and strategy.choices)
        result: dict[str, JsonValue] = {
            "product": product,
            "strategy_present": strategy is not None,
            "strategy_state": "review_required" if pending else "validated",
            "approval_state": current_check(self._approvals, profile).state,
            "envelope": describe_envelope(profile).model_dump(mode="json"),
        }
        if context is not None:
            result["basis_context"] = context.model_dump(mode="json")
            result["basis_status"] = "engine_unavailable"
        return result

    def diff(self, product: str) -> dict[str, JsonValue]:
        """Classifica diferença estrutural em relação ao comportamento legado."""
        data = self.inspect(product)
        pending = data["strategy_state"] == "review_required"
        present = data["strategy_present"] is True
        data.update(
            {
                "changes": ["strategy"] if present else [],
                "classification": "pending" if pending else "automatic",
            }
        )
        return data

    def compile(self, product: str) -> dict[str, JsonValue]:
        """Compila prévia simbólica, sem alegar cobertura efetivamente executada."""
        info = self.inspect(product)
        strategy = load_strategy(self._store, product)
        if strategy is not None:
            strategy.ensure_compilable(self._clock.now())
        profile = self._profiles.load(product)
        spec = self._specs.load(product, profile)
        flows = self._documents.load_flows(product)
        return {
            **info,
            "preview": preview(profile, spec, flows).model_dump(mode="json"),
            "executed": False,
        }

    def migrate(self, product: str, output: str) -> dict[str, JsonValue]:
        """Gera cópia de estratégia neutra sem modificar perfil ou aprovação."""
        self._profiles.load(product)
        if load_strategy(self._store, product) is not None:
            raise ConfigError("O produto já possui estratégia; a migração exige perfil legado.")
        name = self._store.migrate(product, output)
        return {
            "product": product,
            "copy": name,
            "changes": ["strategy_added"],
            "classification": "automatic",
            "approval_changed": False,
        }
