"""Validação e prévia local de estratégia sem abrir transporte ou conceder autorização."""

from datetime import UTC

from harness_dast.application.ports import (
    ApprovalStore,
    Clock,
    ProductDocuments,
    ProfileRepository,
    ReferencedFile,
    StrategyStore,
)
from harness_dast.application.scope_approval import current_check
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.envelope import describe_envelope
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy import Strategy


def load_strategy(store: StrategyStore, product: str) -> Strategy | None:
    """Lê estratégia opcional e confere suas referências reais."""
    data = store.read(product)
    if data is None:
        return None
    strategy = Strategy.from_data(data)
    store.check_references(product, strategy.references)
    return strategy


class StrategyProfiles:
    """Recusa estratégia inválida ou pendente na fronteira de comandos com tráfego."""

    def __init__(self, inner: ProfileRepository, store: StrategyStore, clock: Clock) -> None:
        """Recebe perfil, armazenamento e relógio."""
        self._inner, self._store, self._clock = inner, store, clock

    def load(self, product: str) -> ProductProfile:
        """Carrega perfil e valida estratégia presente antes de executar."""
        profile = self._inner.load(product)
        strategy = load_strategy(self._store, product)
        if strategy is not None:
            strategy.ensure_compilable(self._clock.now())
        return profile

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Lista documentos ausentes do perfil subjacente."""
        return self._inner.missing_files(product, profile)


class StrategyService:
    """Consulta e migra estratégia sem tráfego ou mudança de aprovação."""

    def __init__(
        self,
        profiles: ProfileRepository,
        store: StrategyStore,
        approvals: ApprovalStore,
        clock: Clock,
        documents: ProductDocuments,
    ) -> None:
        """Recebe as portas necessárias às operações locais."""
        self._profiles, self._store = profiles, store
        self._approvals, self._clock = approvals, clock
        self._documents = documents

    def inspect(self, product: str) -> dict[str, JsonValue]:
        """Descreve estratégia, estado de aprovação e envelope sem exigir aprovação."""
        profile = self._profiles.load(product)
        strategy = load_strategy(self._store, product)
        self._documents.load_data_rules(product)
        self._documents.load_flows(product)
        pending = bool(
            strategy
            and any(
                c.state != "validated" or c.valid_until < self._clock.now().astimezone(UTC).date()
                for c in strategy.choices
            )
        )
        return {
            "product": product,
            "strategy_present": strategy is not None,
            "strategy_state": "review_required" if pending else "validated",
            "approval_state": current_check(self._approvals, profile).state,
            "envelope": describe_envelope(profile).model_dump(mode="json"),
        }

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
        return {**info, "coverage": "pending_probe_and_zap", "executed": False}

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
