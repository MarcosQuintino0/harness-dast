"""Aprovação humana dos blocos de proteção do perfil (ADR 0037).

`ScopeApproval` é o registro que uma pessoa gera ao aprovar: produto, impressão digital (geral
e por bloco), instante e um resumo legível do que foi aprovado. Nunca contém segredo.
`check_approval` compara o registro com o perfil atual e decide: aprovado, nunca aprovado,
alterado desde a aprovação (e quais blocos) ou inválido. `ApprovalCheck.ensure_approved`
transforma qualquer coisa diferente de "aprovado" em `ScopeNotApproved` (falha fechada).

O módulo é puro: o instante entra por argumento e a gravação é de um adaptador.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harness_dast.domain.errors import ScopeNotApproved
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run import SLUG_PATTERN
from harness_dast.domain.scope_fingerprint import (
    BLOCK_IDS,
    FINGERPRINT_VERSION,
    block_digests,
    combine_digests,
    describe_block,
)
from harness_dast.domain.window import ensure_aware

ApprovalState = Literal["approved", "not_approved", "changed", "invalid"]
APPROVE_COMMAND = "hdast profile approve"
_SHA256_LENGTH = 64
_MAX_SUMMARY_LINES = 300
_MAX_LINE = 6000
_HEX = frozenset("0123456789abcdef")


def _is_sha256(value: str) -> bool:
    return len(value) == _SHA256_LENGTH and set(value) <= _HEX


class ScopeApproval(BaseModel):
    """Registro da aprovação de um produto.

    Attributes:
        schema_version: Versão do cálculo da impressão digital (`FINGERPRINT_VERSION`).
        product: Slug do produto aprovado.
        digest: SHA-256 geral, calculado de `product` e `blocks`.
        blocks: SHA-256 de cada bloco de proteção, por identificador.
        approved_at: Instante da aprovação (ISO 8601 com fuso).
        summary: Resumo legível do que a pessoa viu e aprovou.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    product: str = Field(pattern=rf"^{SLUG_PATTERN}$")
    digest: str
    blocks: dict[str, str] = Field(max_length=len(BLOCK_IDS))
    approved_at: str = Field(max_length=64)
    summary: tuple[str, ...] = Field(max_length=_MAX_SUMMARY_LINES)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Linhas curtas e imprimíveis: o resumo é só para ler."""
        if any(len(line) > _MAX_LINE or not line.isprintable() for line in value):
            raise ValueError("linha do resumo longa demais ou com caractere não imprimível")
        return value

    @model_validator(mode="after")
    def validate_digests(self) -> Self:
        """Exige resumos SHA-256 bem formados e coerentes entre si.

        O resumo geral precisa ser o que sai dos resumos por bloco e do produto: um registro
        editado à mão (um só dos dois) deixa de bater e é recusado.
        """
        if not _is_sha256(self.digest) or not all(
            _is_sha256(value) for value in self.blocks.values()
        ):
            raise ValueError("resumo (SHA-256) malformado")
        if combine_digests(self.product, self.blocks) != self.digest:
            raise ValueError("resumo geral não confere com os resumos dos blocos")
        return self


@dataclass(frozen=True)
class ApprovalCheck:
    """Resultado de comparar o perfil com a aprovação gravada.

    Attributes:
        product: Produto conferido.
        state: Estado da aprovação.
        changed_blocks: Blocos alterados desde a aprovação (só com `state == "changed"`).
        approved_at: Instante da aprovação, quando há registro válido.
    """

    product: str
    state: ApprovalState
    changed_blocks: tuple[str, ...] = ()
    approved_at: str | None = None

    def message(self) -> str:
        """Frase que diz o que houve, sem repetir valor do perfil."""
        if self.state == "approved":
            return f"O escopo de {self.product} está aprovado ({self.approved_at})."
        if self.state == "changed":
            names = "; ".join(f"{block} ({describe_block(block)})" for block in self.changed_blocks)
            return (
                f"O perfil de {self.product} mudou desde a aprovação de {self.approved_at}. "
                f"Blocos alterados: {names or 'resumo geral diferente'}."
            )
        if self.state == "invalid":
            return (
                f"A aprovação do escopo de {self.product} está ilegível, é de outra versão do "
                "cálculo ou de outro produto; vale como NÃO aprovada."
            )
        return f"O escopo de {self.product} ainda não foi aprovado por uma pessoa."

    def ensure_approved(self) -> None:
        """Garante que o escopo está aprovado.

        Raises:
            ScopeNotApproved: Em qualquer estado diferente de `approved`; a dica manda uma
                pessoa rodar o comando de aprovação (o agente não pode).
        """
        if self.state == "approved":
            return
        raise ScopeNotApproved(
            self.message(),
            hint=f"Uma pessoa precisa revisar e aprovar, num terminal: {APPROVE_COMMAND} "
            f"{self.product}. O agente de IA não aprova.",
            state=self.state,
            changed_blocks=self.changed_blocks,
        )


def _changed(approval: ScopeApproval, current: dict[str, str]) -> tuple[str, ...]:
    names = set(approval.blocks) | set(current)
    order = {block: index for index, block in enumerate(BLOCK_IDS)}
    differing = [name for name in names if approval.blocks.get(name) != current.get(name)]
    return tuple(sorted(differing, key=lambda name: (order.get(name, len(order)), name)))


def check_approval(profile: ProductProfile, approval: ScopeApproval | None) -> ApprovalCheck:
    """Compara o perfil com a aprovação gravada.

    Args:
        profile: Perfil validado, como está agora.
        approval: Registro gravado, ou `None` se nunca houve aprovação.

    Returns:
        O resultado. Registro de outro produto vale `invalid`; registro de outra versão do
        cálculo nem chega aqui (o modelo o recusa na leitura).
    """
    if approval is None:
        return ApprovalCheck(product=profile.product, state="not_approved")
    if approval.product != profile.product:
        return ApprovalCheck(product=profile.product, state="invalid")
    current = block_digests(profile)
    if approval.digest == combine_digests(profile.product, current) and approval.blocks == current:
        return ApprovalCheck(
            product=profile.product, state="approved", approved_at=approval.approved_at
        )
    return ApprovalCheck(
        product=profile.product,
        state="changed",
        changed_blocks=_changed(approval, current),
        approved_at=approval.approved_at,
    )


def create_approval(
    profile: ProductProfile, approved_at: datetime, summary: tuple[str, ...]
) -> ScopeApproval:
    """Monta o registro de aprovação do perfil no instante dado.

    Raises:
        ConfigError: Se `approved_at` não tiver fuso.
    """
    ensure_aware(approved_at)
    blocks = block_digests(profile)
    return ScopeApproval(
        schema_version=FINGERPRINT_VERSION,
        product=profile.product,
        digest=combine_digests(profile.product, blocks),
        blocks=blocks,
        approved_at=approved_at.isoformat(),
        summary=summary,
    )
