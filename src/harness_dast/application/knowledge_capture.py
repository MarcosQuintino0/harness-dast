"""Captura e verificação de referências de conhecimento sem alcançar o alvo."""

from harness_dast.application.common_ports import (
    ApprovalStore,
    Clock,
    ProductDocuments,
    ProfileRepository,
    SpecLoader,
    StrategyDependencyStore,
    ZapControl,
)
from harness_dast.application.knowledge_observations import from_run
from harness_dast.application.knowledge_ports import KnowledgeRunStore, KnowledgeStore
from harness_dast.application.scope_approval import current_check
from harness_dast.application.strategy import basis_for_engine
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge import Knowledge, KnowledgeEntry
from harness_dast.domain.strategy import StrategyReferences
from harness_dast.domain.strategy_control import ensure_capture_control_url
from harness_dast.domain.strategy_preview import preview


class CaptureKnowledge:
    """Cria cópia vinculada às fontes atuais, sem ativar nem autorizar escopo."""

    def __init__(
        self,
        profiles: ProfileRepository,
        store: KnowledgeStore,
        dependencies: StrategyDependencyStore,
        approvals: ApprovalStore,
        clock: Clock,
        documents: ProductDocuments,
        specs: SpecLoader,
        zap: ZapControl,
        control_url: str,
        runs: KnowledgeRunStore | None = None,
    ) -> None:
        """Recebe fontes independentes, relógio e controle local do motor."""
        self._profiles, self._store, self._deps, self._approvals = (
            profiles,
            store,
            dependencies,
            approvals,
        )
        self._clock, self._documents, self._specs, self._zap = clock, documents, specs, zap
        self._control_url = control_url
        self._runs = runs

    def execute(self, product: str, run_id: str | None = None) -> dict[str, JsonValue]:
        """Valida documentos e aprovação, e cria cópia sem enviar pedido ao alvo."""
        profile = self._profiles.load(product)
        current_check(self._approvals, profile).ensure_approved()
        profile.scope.authorization.ensure_valid(self._clock.now())
        original = self._store.read(product)
        if original is not None:
            raise ConfigError("Captura exige knowledge.yml ausente.")
        data = self._documents.load_data_rules(product)
        flows = self._documents.load_flows(product)
        spec = self._specs.load(product, profile)
        if data is not None:
            data.validate_against(spec)
        if flows is not None:
            flows.validate_against(spec)
        preview(profile, spec, flows)
        dependencies = self._deps.read_dependencies(product, profile)
        ensure_capture_control_url(self._control_url, profile.environment.base_url)
        version = self._zap.version()
        basis = basis_for_engine(self._deps, product, profile, version)
        if basis is None:
            raise ConfigError("Motor indisponível para captura de conhecimento.")
        if (
            self._profiles.load(product) != profile
            or self._store.read(product) != original
            or self._deps.read_dependencies(product, profile) != dependencies
        ):
            raise ConfigError("Fontes mudaram durante a captura; repita a operação.")
        current_check(self._approvals, profile).ensure_approved()
        profile.scope.authorization.ensure_valid(self._clock.now())
        common = {
            "reason": "references_existing_documents",
            "source": "contract",
            "state": "proposed",
            "valid_until": profile.scope.authorization.valid_until,
        }
        entries = tuple(
            KnowledgeEntry.model_validate(
                {
                    **common,
                    "kind": kind,
                    "dependencies": (*deps, "planning"),
                    "state": "proposed",
                }
            )
            for kind, deps in (
                ("account", ("environment", "authorization", "accounts", "engine")),
                ("data", ("environment", "authorization", "openapi", "data_rules", "engine")),
                ("flow", ("environment", "authorization", "openapi", "flows", "engine")),
                (
                    "effect",
                    ("environment", "authorization", "accounts", "openapi", "flows", "engine"),
                ),
                ("authentication", ("environment", "authorization", "accounts", "engine")),
            )
        )
        knowledge = Knowledge(
            schema_version=1,
            basis=basis,
            references=StrategyReferences(
                target="target.yml", data_rules="data-rules.yml", flows="flows.yml"
            ),
            entries=entries,
        )
        if run_id is not None:
            if self._runs is None:
                raise ConfigError("Leitor de execucoes indisponivel.")
            observed = self._runs.read(run_id)
            knowledge = from_run(
                knowledge,
                observed,
                profile,
                spec,
                data,
                flows,
                self._documents.hashes(product, profile),
                version,
            )
            current = self._runs.read(run_id).provenance
            initial = observed.provenance
            if (
                self._deps.read_dependencies(product, profile) != dependencies
                or current.run_id != initial.run_id
                or current.manifest_sha256 != initial.manifest_sha256
                or current.probe_sha256 != initial.probe_sha256
                or current.authz_sha256 != initial.authz_sha256
                or self._profiles.load(product) != profile
            ):
                raise ConfigError("Fontes mudaram durante a captura; repita a operacao.")
            current_check(self._approvals, profile).ensure_approved()
            profile.scope.authorization.ensure_valid(self._clock.now())
        name = self._store.write_capture(product, knowledge.model_dump(mode="json"))
        return {"product": product, "copy": name, "activated": False, "approval_changed": False}
