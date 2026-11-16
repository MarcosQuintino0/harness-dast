"""Revalidação do conhecimento ativo antes de carregar documentos reutilizados."""

from harness_dast.application.ports import (
    Clock,
    KnowledgeStore,
    ProfileRepository,
    ReferencedFile,
    StrategyDependencyStore,
    ZapControl,
)
from harness_dast.application.strategy import basis_for_engine
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge import Knowledge
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
        self._deps.check_references(product, knowledge.references)
        if self._zap is None:
            raise ConfigError("Não é possível validar conhecimento sem o motor atual.")
        basis = basis_for_engine(self._deps, product, profile, self._zap.version())
        if basis is None:
            raise ConfigError("Motor indispon?vel para validar conhecimento.")
        checks = knowledge.review(basis, self._clock.now())
        if any(
            reasons
            for entry, reasons in zip(knowledge.entries, checks, strict=True)
            if entry.kind != "effect"
        ):
            raise ConfigError(
                "Conhecimento vencido ou fontes alteradas; revise antes de reutilizar."
            )
        return profile

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Mantém a verificação de arquivos do repositório subjacente."""
        return self._inner.missing_files(product, profile)
