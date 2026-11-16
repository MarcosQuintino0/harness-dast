"""Frescor da pilha: comparação dos hashes e o erro `STACK_STALE` (ADR 0081)."""

import pytest
from pydantic import ValidationError

from harness_dast.domain.errors import ExitCode, StackStale
from harness_dast.domain.stack_binding import (
    StackDigests,
    compare_digests,
    is_stale_refusal,
    proxy_refusal_error,
    stale_error,
    unbound_freshness,
    unreadable_freshness,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
BODY = b"hdast scope-proxy: request refused\n"


def test_compare_digests_fresh_quando_os_dois_hashes_sao_iguais() -> None:
    same = StackDigests(profile_sha256=A, approval_sha256=B)

    result = compare_digests(same, StackDigests(profile_sha256=A, approval_sha256=B))

    assert result.state == "fresh"
    assert result.stale_parts == ()


@pytest.mark.parametrize(
    ("current", "parts"),
    [
        (StackDigests(profile_sha256=C, approval_sha256=B), ("profile",)),
        (StackDigests(profile_sha256=A, approval_sha256=C), ("approval",)),
        (StackDigests(profile_sha256=C, approval_sha256=C), ("profile", "approval")),
        (StackDigests(profile_sha256=None, approval_sha256=B), ("profile",)),
        (StackDigests(profile_sha256=A, approval_sha256=None), ("approval",)),
        (StackDigests(), ("profile", "approval")),
    ],
)
def test_compare_digests_stale_quando_algum_arquivo_diverge_ou_sumiu(
    current: StackDigests, parts: tuple[str, ...]
) -> None:
    recorded = StackDigests(profile_sha256=A, approval_sha256=B)

    result = compare_digests(recorded, current)

    assert result.state == "stale"
    assert result.stale_parts == parts
    assert A not in result.message
    assert "approval_changed" in result.message


@pytest.mark.parametrize("bad", ["", "xyz", "A" * 64, "a" * 63, "a" * 65])
def test_stack_digests_recusa_hash_malformado(bad: str) -> None:
    with pytest.raises(ValidationError):
        StackDigests(profile_sha256=bad)


def test_stale_error_usa_a_saida_de_verificacao_previa_e_manda_recriar_a_pilha() -> None:
    freshness = compare_digests(
        StackDigests(profile_sha256=A, approval_sha256=B),
        StackDigests(profile_sha256=C, approval_sha256=B),
    )

    error = stale_error(freshness, "meu-produto")

    assert isinstance(error, StackStale)
    assert error.code == "STACK_STALE"
    assert error.exit_code == ExitCode.PREFLIGHT
    assert error.stale_parts == ("profile",)
    assert error.hint is not None
    assert "hdast stack down" in error.hint
    assert "hdast stack up meu-produto" in error.hint
    assert "profile approve" not in error.hint


def test_stale_error_lembra_que_a_aprovacao_e_de_uma_pessoa_quando_ela_mudou() -> None:
    freshness = compare_digests(
        StackDigests(profile_sha256=A, approval_sha256=B),
        StackDigests(profile_sha256=A, approval_sha256=C),
    )

    error = stale_error(freshness, "p")

    assert error.hint is not None
    assert "uma pessoa" in error.hint


def test_vinculo_ilegivel_falha_fechado_e_vinculo_ausente_nao_compara() -> None:
    unreadable = unreadable_freshness()

    assert unreadable.state == "unreadable"
    assert unreadable.stale_parts == ("binding",)
    assert stale_error(unreadable, "p").stale_parts == ("binding",)
    assert unbound_freshness().state == "unbound"


def test_is_stale_refusal_exige_403_motivo_e_corpo_do_proxy() -> None:
    assert is_stale_refusal(403, "approval_changed", BODY)
    assert is_stale_refusal(403, " Approval_Changed ", BODY)


@pytest.mark.parametrize(
    ("status", "reason", "body"),
    [
        (200, "approval_changed", BODY),
        (502, "approval_changed", BODY),
        (403, None, BODY),
        (403, "", BODY),
        (403, "deny_path", BODY),
        (403, "path_not_allowed", BODY),
        (403, "approval_changed", b""),
        (403, "approval_changed", b"Forbidden"),
    ],
)
def test_is_stale_refusal_ignora_outras_respostas(
    status: int, reason: str | None, body: bytes
) -> None:
    assert not is_stale_refusal(status, reason, body)


def test_proxy_refusal_error_diz_que_nao_e_achado_nem_recusa_de_escopo() -> None:
    error = proxy_refusal_error()

    assert error.code == "STACK_STALE"
    assert "approval_changed" in error.message
    assert "não é achado" in error.message
    assert error.hint is not None
    assert "hdast stack down" in error.hint
