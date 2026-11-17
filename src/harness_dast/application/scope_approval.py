"""Casos de uso da aprovação humana do escopo (ADR 0037).

- `ApprovedProfileRepository`: o ponto central da conferência. É um `ProfileRepository` que só
  devolve o perfil se uma pessoa aprovou os blocos de proteção e eles não mudaram desde então.
  Todo comando que toca o alvo (`preflight`, `probe`, `scan`, `authz`, `run`, `cleanup` e
  `stack up`) recebe esta versão do repositório; os comandos só de leitura recebem a comum.
- `ScopeApprovals.approve`: só uma pessoa, em terminal interativo, diante do resumo.
- `ScopeApprovals.status`: consulta, liberada ao agente (só lê).
"""

from pydantic import BaseModel, ConfigDict

from harness_dast.application.common_ports import (
    ApprovalStore,
    Clock,
    ProfileRepository,
    ReferencedFile,
)
from harness_dast.application.scope_approval_ports import ApprovalPrompt
from harness_dast.domain.errors import ConfigError, ScopeNotApproved
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_approval import (
    APPROVE_COMMAND,
    ApprovalCheck,
    ApprovalState,
    check_approval,
    create_approval,
)
from harness_dast.domain.scope_approval_summary import describe_protection
from harness_dast.domain.scope_fingerprint import describe_block


class ApprovalInfo(BaseModel):
    """Estado da aprovação de um produto, como o agente e a pessoa o veem.

    Attributes:
        state: `approved`, `not_approved`, `changed` ou `invalid`.
        approved_at: Instante da aprovação vigente ou anterior; `None` sem registro válido.
        changed_blocks: Blocos alterados desde a aprovação (só com `changed`).
        message: Frase que diz o que houve.
    """

    model_config = ConfigDict(frozen=True)

    state: ApprovalState
    approved_at: str | None
    changed_blocks: tuple[str, ...]
    message: str


class ApproveReport(BaseModel):
    """Resultado de `profile approve`.

    Attributes:
        product: Produto.
        approved: `True` se há aprovação vigente ao fim (nova ou já existente); `False` se a
            pessoa não confirmou (nada foi gravado).
        already_approved: `True` se o perfil já estava aprovado e nada foi regravado.
        approved_at: Instante da aprovação vigente, ou `None` se a pessoa não confirmou.
        changed_blocks: Blocos que mudaram desde a aprovação anterior (vazio se era a primeira).
        summary: Resumo do que foi mostrado à pessoa.
    """

    model_config = ConfigDict(frozen=True)

    product: str
    approved: bool
    already_approved: bool
    approved_at: str | None
    changed_blocks: tuple[str, ...]
    summary: tuple[str, ...]


def current_check(store: ApprovalStore, profile: ProductProfile) -> ApprovalCheck:
    """Confere o perfil com a aprovação gravada; registro ilegível vale `invalid`."""
    try:
        approval = store.read(profile.product)
    except ScopeNotApproved:
        return ApprovalCheck(product=profile.product, state="invalid")
    return check_approval(profile, approval)


def info_of(check: ApprovalCheck) -> ApprovalInfo:
    """Traduz o resultado da conferência para o modelo de saída."""
    return ApprovalInfo(
        state=check.state,
        approved_at=check.approved_at,
        changed_blocks=check.changed_blocks,
        message=check.message(),
    )


class ApprovedProfileRepository:
    """`ProfileRepository` que recusa perfil sem aprovação humana vigente (falha fechada)."""

    def __init__(self, inner: ProfileRepository, store: ApprovalStore) -> None:
        """Cria o repositório conferido.

        Args:
            inner: Repositório comum (lê e valida o perfil).
            store: Guarda das aprovações.
        """
        self._inner = inner
        self._store = store

    def load(self, product: str) -> ProductProfile:
        """Carrega o perfil e confere a aprovação dos blocos de proteção.

        Raises:
            ConfigError: Como `ProfileRepository.load` (perfil inválido tem prioridade).
            ScopeNotApproved: Nunca aprovado, alterado desde a aprovação ou aprovação inválida.
        """
        profile = self._inner.load(product)
        current_check(self._store, profile).ensure_approved()
        return profile

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Veja `ProfileRepository.missing_files`."""
        return self._inner.missing_files(product, profile)


class ScopeApprovals:
    """Aprovar (só por pessoa) e consultar a aprovação do escopo de um produto."""

    def __init__(
        self,
        profiles: ProfileRepository,
        store: ApprovalStore,
        prompt: ApprovalPrompt,
        clock: Clock,
    ) -> None:
        """Cria o caso de uso.

        Args:
            profiles: Repositório COMUM de perfis (aprovar não exige estar aprovado).
            store: Guarda das aprovações.
            prompt: Confirmação digitada, em terminal.
            clock: Relógio injetado (instante da aprovação).
        """
        self._profiles = profiles
        self._store = store
        self._prompt = prompt
        self._clock = clock

    def status(self, product: str) -> ApprovalInfo:
        """Estado da aprovação do produto (só lê).

        Raises:
            ConfigError: Produto ou perfil inválido.
        """
        return info_of(current_check(self._store, self._profiles.load(product)))

    def approve(self, product: str, *, interactive: bool) -> ApproveReport:
        """Mostra os blocos de proteção e grava a aprovação se a pessoa confirmar.

        Args:
            product: Slug do produto.
            interactive: Se há terminal interativo e a saída não é `--json`; a CLI calcula.

        Raises:
            ConfigError: Sem terminal interativo (o agente não aprova), produto ou perfil
                inválido, ou falha ao gravar.
        """
        if not interactive:
            raise ConfigError(
                "Só uma pessoa, em terminal interativo, aprova o escopo do produto.",
                hint=f"Rode no seu terminal, sem --json e sem redirecionar a entrada: "
                f"{APPROVE_COMMAND} {product}",
            )
        profile = self._profiles.load(product)
        check = current_check(self._store, profile)
        summary = describe_protection(profile)
        if check.state == "approved":
            return ApproveReport(
                product=product,
                approved=True,
                already_approved=True,
                approved_at=check.approved_at,
                changed_blocks=(),
                summary=summary,
            )
        changes = tuple(f"{block}: {describe_block(block)}" for block in check.changed_blocks)
        if not self._prompt.confirm(product, summary, changes):
            return ApproveReport(
                product=product,
                approved=False,
                already_approved=False,
                approved_at=None,
                changed_blocks=check.changed_blocks,
                summary=summary,
            )
        approval = create_approval(profile, self._clock.now(), summary)
        self._store.write(approval)
        return ApproveReport(
            product=product,
            approved=True,
            already_approved=False,
            approved_at=approval.approved_at,
            changed_blocks=check.changed_blocks,
            summary=summary,
        )
