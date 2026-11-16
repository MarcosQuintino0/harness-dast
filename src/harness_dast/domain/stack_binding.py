"""Frescor da pilha: o vínculo gravado pelo `stack up` contra os arquivos de agora (ADR 0081).

O proxy de escopo gerenciado prende o hash SHA-256 completo do `target.yml` e da aprovação no
`stack up` e nega todo pedido (`approval_changed`) se um deles mudar. Este módulo compara os
dois lados antes de qualquer pedido ao alvo e monta o erro `StackStale` que diz o que fazer.

O que garante: a comparação é pura e falha fechada (arquivo ausente ou ilegível conta como
divergente); a mensagem nunca traz o hash. O que não faz: não lê arquivo, não decide escopo e
não afrouxa o proxy.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from harness_dast.domain.errors import StackStale

PROXY_REASON_HEADER: Final = "X-Hdast-Reason"
"""Cabeçalho com que o proxy de escopo explica a recusa."""

STALE_PROXY_REASON: Final = "approval_changed"
"""Motivo do proxy quando perfil ou aprovação mudaram depois do `stack up`."""

PROXY_REFUSAL_STATUS: Final = 403
PROXY_REFUSAL_BODY_PREFIX: Final = b"hdast scope-proxy:"
RECREATE_COMMANDS: Final = "hdast stack down e depois hdast stack up <produto>"

BindingState = Literal["fresh", "stale", "unbound", "unreadable"]

_PART_LABELS: Final = {
    "profile": "o perfil (target.yml)",
    "approval": "a aprovação do escopo",
}


class StackDigests(BaseModel):
    """Hashes SHA-256 (hexadecimais) do perfil e da aprovação; `None` com o arquivo ausente."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    approval_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class StackFreshness(BaseModel):
    """Resultado da conferência do frescor da pilha.

    Attributes:
        state: `fresh` (iguais), `stale` (divergem), `unbound` (a política não prende fontes:
            nada a comparar) ou `unreadable` (vínculo ausente ou ilegível).
        stale_parts: O que divergiu (`profile`, `approval`, `binding`); vazio fora de `stale`
            e `unreadable`.
        message: Frase pronta para a pessoa, com o que fazer quando não está fresca.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: BindingState
    stale_parts: tuple[str, ...] = ()
    message: str


def compare_digests(recorded: StackDigests, current: StackDigests) -> StackFreshness:
    """Compara o vínculo gravado com os arquivos de agora; só hash idêntico vale `fresh`."""
    parts = tuple(
        part
        for part, same in (
            ("profile", recorded.profile_sha256 == current.profile_sha256),
            ("approval", recorded.approval_sha256 == current.approval_sha256),
        )
        if not same
    )
    if not parts:
        return StackFreshness(state="fresh", message="A pilha corresponde ao perfil e à aprovação.")
    return StackFreshness(state="stale", stale_parts=parts, message=_stale_message(parts))


def unbound_freshness() -> StackFreshness:
    """A política da pilha não prende fontes (política escrita à mão): nada a comparar."""
    return StackFreshness(
        state="unbound", message="A política da pilha não prende perfil nem aprovação."
    )


def unreadable_freshness() -> StackFreshness:
    """O vínculo da pilha está ausente ou ilegível; falha fechada, como o proxy."""
    return StackFreshness(
        state="unreadable",
        stale_parts=("binding",),
        message=(
            "O vínculo que o stack up gravou na política da pilha ativa está ausente ou ilegível; "
            "o proxy de escopo falha fechado nesse caso e nada foi enviado ao alvo."
        ),
    )


def stale_error(freshness: StackFreshness, product: str) -> StackStale:
    """Monta o erro `STACK_STALE` para uma conferência que não deu `fresh`."""
    return StackStale(
        freshness.message,
        hint=_recreate_hint(product, freshness.stale_parts),
        stale_parts=freshness.stale_parts,
    )


def proxy_refusal_error() -> StackStale:
    """Erro para o 403 `approval_changed` que o proxy devolveu no meio da execução."""
    return StackStale(
        "O proxy de escopo recusou o pedido (403, approval_changed): o perfil ou a aprovação "
        "mudou depois do stack up e a pilha nega tudo até ser recriada. Isto não é achado nem "
        "recusa de escopo comum.",
        hint=f"Recrie a pilha: {RECREATE_COMMANDS}. Se a aprovação mudou, uma pessoa precisa "
        "rodar hdast profile approve antes.",
    )


def is_stale_refusal(status: int, reason: str | None, body: bytes) -> bool:
    """Diz se a resposta é a recusa `approval_changed` do proxy de escopo.

    Exige as três marcas (403, cabeçalho de motivo e a frase fixa do corpo) para um alvo comum
    não disparar o erro por acaso. Alvo malicioso que as forje só consegue parar a execução, o
    que é a direção segura.
    """
    return (
        status == PROXY_REFUSAL_STATUS
        and (reason or "").strip().lower() == STALE_PROXY_REASON
        and body.startswith(PROXY_REFUSAL_BODY_PREFIX)
    )


def _stale_message(parts: tuple[str, ...]) -> str:
    named = " e ".join(_PART_LABELS[part] for part in parts if part in _PART_LABELS)
    return (
        f"Desde o stack up da pilha ativa mudou {named}. O proxy de escopo prende o hash do "
        "arquivo e negaria todo pedido (approval_changed); nada foi enviado ao alvo."
    )


def _recreate_hint(product: str, parts: tuple[str, ...]) -> str:
    text = f"Recrie a pilha: hdast stack down e depois hdast stack up {product}."
    if "approval" in parts:
        text += " Se a aprovação mudou, uma pessoa precisa rodar hdast profile approve antes."
    return text
