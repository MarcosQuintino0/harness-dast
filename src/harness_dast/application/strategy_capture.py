"""Captura explícita de uma estratégia neutra sem pedidos ao alvo."""

from harness_dast.application.ports import (
    ApprovalStore,
    Clock,
    ProductDocuments,
    ProfileRepository,
    SpecLoader,
    StrategyCaptureStore,
    ZapControl,
)
from harness_dast.application.scope_approval import current_check
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.strategy import Strategy
from harness_dast.domain.strategy_basis import digest_strategy_document
from harness_dast.domain.strategy_capture import capture_strategy
from harness_dast.domain.strategy_control import ensure_capture_control_url
from harness_dast.domain.strategy_preview import preview


class CaptureStrategy:
    """Valida as fontes atuais e cria uma cópia sem ativar nem alterar aprovação."""

    def __init__(
        self,
        profiles: ProfileRepository,
        store: StrategyCaptureStore,
        approvals: ApprovalStore,
        clock: Clock,
        documents: ProductDocuments,
        specs: SpecLoader,
        zap: ZapControl,
        control_url: str,
    ) -> None:
        """Recebe portas locais e controle do ZAP da execução atual."""
        self._profiles, self._store, self._approvals = profiles, store, approvals
        self._clock, self._documents, self._specs, self._zap = clock, documents, specs, zap
        self._control_url = control_url

    def execute(self, product: str, output: str) -> dict[str, JsonValue]:
        """Confere aprovação e fontes antes de consultar o motor e gravar cópia."""
        profile = self._profiles.load(product)
        current_check(self._approvals, profile).ensure_approved()
        now = self._clock.now()
        profile.scope.authorization.ensure_valid(now)
        existing = self._store.read(product)
        if existing is not None:
            strategy = Strategy.from_data(existing)
            self._store.check_references(product, strategy.references)
            if strategy.choices:
                raise ConfigError("A captura exige estratégia ausente ou sem escolhas.")
        self._documents.load_data_rules(product)
        flows = self._documents.load_flows(product)
        spec = self._specs.load(product, profile)
        preview(profile, spec, flows)
        contract, rules, flows_bytes = self._store.read_dependencies(product, profile)
        ensure_capture_control_url(self._control_url, profile.environment.base_url)
        version = self._zap.version()
        if (
            self._profiles.load(product) != profile
            or self._store.read(product) != existing
            or self._store.read_dependencies(product, profile) != (contract, rules, flows_bytes)
        ):
            raise ConfigError("As fontes mudaram durante a captura; execute novamente.")
        current_check(self._approvals, profile).ensure_approved()
        strategy = capture_strategy(
            profile,
            self._approvals.read(product),
            self._clock.now(),
            openapi_sha256=digest_strategy_document(contract),
            data_rules_sha256=digest_strategy_document(rules),
            flows_sha256=digest_strategy_document(flows_bytes),
            engine_version=version,
        )
        name = self._store.write_capture(product, output, strategy)
        return {
            "product": product,
            "copy": name,
            "changes": ["strategy_bound"],
            "classification": "automatic",
            "approval_changed": False,
            "activated": False,
        }
