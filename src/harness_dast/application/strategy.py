"""Validação e prévia local de estratégia sem abrir transporte ou conceder autorização."""

from typing import Protocol

from harness_dast.application.ports import ApprovalStore, Clock, ProfileRepository, ReferencedFile
from harness_dast.application.scope_approval import current_check
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.envelope import describe_envelope
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy import Strategy


class StrategyStore(Protocol):
    """Fronteira de armazenamento de estratégia do produto."""

    def read(self, product: str) -> dict[str, object] | None:
        """Lê a estratégia ou devolve None quando ausente."""
        ...

    def check_references(self, product: str) -> None:
        """Confere contenção das referências."""
        ...

    def migrate(self, product: str, output: str) -> str:
        """Cria cópia neutra sem sobrescrever."""
        ...


def load_strategy(store: StrategyStore, product: str) -> Strategy | None:
    """Lê estratégia opcional e confere suas referências reais."""
    data = store.read(product)
    if data is None:
        return None
    strategy = Strategy.from_data(data)
    store.check_references(product)
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
    ) -> None:
        """Recebe as portas necessárias às operações locais."""
        self._profiles, self._store = profiles, store
        self._approvals, self._clock = approvals, clock

    def inspect(self, product: str) -> dict[str, JsonValue]:
        """Descreve estratégia, estado de aprovação e envelope sem exigir aprovação."""
        profile = self._profiles.load(product)
        strategy = load_strategy(self._store, product)
        pending = bool(
            strategy
            and any(
                c.state != "validated" or c.valid_until < self._clock.now().date()
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
        name = self._store.migrate(product, output)
        return {
            "product": product,
            "copy": name,
            "changes": ["strategy_added"],
            "classification": "automatic",
            "approval_changed": False,
        }
