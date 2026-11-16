"""Frescor da pilha: recusa, antes do primeiro pedido, a pilha criada com outro perfil (ADR 0081).

O proxy de escopo prende o hash do `target.yml` e da aprovação no `stack up`. Este caso de uso
compara esse vínculo com os arquivos de agora e, se divergirem, levanta `StackStale` com o que
fazer. Também alimenta o `stack status`.

O que garante: sem pilha gerenciada, ou com a pilha de outro produto, não decide nada (a pilha
não é a deste comando); vínculo ausente ou ilegível falha fechado. O que não faz: não envia
pedido, não recria a pilha e não mexe no perfil nem na aprovação.
"""

from pathlib import Path

from harness_dast.application.ports import (
    ProfileRepository,
    ReferencedFile,
    StackBindingSource,
    StackStateStore,
)
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.stack_binding import (
    StackFreshness,
    compare_digests,
    stale_error,
    unbound_freshness,
    unreadable_freshness,
)


class StackFreshnessCheck:
    """Compara o vínculo da pilha ativa com o perfil e a aprovação atuais."""

    def __init__(self, states: StackStateStore, bindings: StackBindingSource) -> None:
        """Cria a conferência.

        Args:
            states: Estado da pilha gerenciada (diz qual política conferir).
            bindings: Leitura do vínculo gravado e dos arquivos de agora.
        """
        self._states = states
        self._bindings = bindings

    def inspect(self) -> StackFreshness | None:
        """Frescor da pilha ativa; `None` quando não há pilha gerenciada.

        Raises:
            ConfigError: Arquivo de estado da pilha inválido.
        """
        state = self._states.load()
        if state is None:
            return None
        return self._of(state.policy_dir, state.product)

    def ensure_fresh(self, product: str) -> None:
        """Garante que a pilha ativa do produto corresponde ao perfil e à aprovação atuais.

        Sem pilha gerenciada, ou com a pilha de outro produto, nada a conferir.

        Raises:
            StackStale: Perfil ou aprovação mudou depois do `stack up`, ou o vínculo está
                ausente ou ilegível.
            ConfigError: Arquivo de estado da pilha inválido.
        """
        state = self._states.load()
        if state is None or state.product != product:
            return
        freshness = self._of(state.policy_dir, product)
        if freshness.state in ("stale", "unreadable"):
            raise stale_error(freshness, product)

    def _of(self, policy_dir: Path, product: str) -> StackFreshness:
        try:
            recorded = self._bindings.recorded(policy_dir)
        except ConfigError:
            return unreadable_freshness()
        if recorded is None:
            return unbound_freshness()
        return compare_digests(recorded, self._bindings.current(product))


class FreshStackProfiles:
    """`ProfileRepository` que recusa carregar o perfil com a pilha ativa desatualizada.

    Vai por cima do repositório aprovado: a aprovação ausente ou alterada (`SCOPE_NOT_APPROVED`)
    tem prioridade. É o ponto único por onde `preflight`, `probe`, `scan`, `authz`, `negative` e
    `run` passam antes do primeiro pedido ao alvo.
    """

    def __init__(self, inner: ProfileRepository, freshness: StackFreshnessCheck) -> None:
        """Cria o repositório conferido.

        Args:
            inner: Repositório que já confere a aprovação.
            freshness: Conferência do frescor da pilha.
        """
        self._inner = inner
        self._freshness = freshness

    def load(self, product: str) -> ProductProfile:
        """Carrega o perfil e confere o frescor da pilha.

        Raises:
            ConfigError: Como `ProfileRepository.load`.
            ScopeNotApproved: Aprovação ausente ou alterada.
            StackStale: A pilha ativa foi criada com outro perfil ou outra aprovação.
        """
        profile = self._inner.load(product)
        self._freshness.ensure_fresh(product)
        return profile

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Veja `ProfileRepository.missing_files`."""
        return self._inner.missing_files(product, profile)
