"""Conferência do frescor da pilha antes do primeiro pedido ao alvo (ADR 0081)."""

from pathlib import Path

import pytest

from harness_dast.application.stack_freshness import FreshStackProfiles, StackFreshnessCheck
from harness_dast.application.stack_models import ComposeProject, StackState
from harness_dast.domain.errors import ConfigError, ScopeNotApproved, StackStale
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.stack_binding import StackDigests
from tests.fakes.profile_data import valid_profile
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.stack import FakeBindingSource, InMemoryStackState

A = StackDigests(profile_sha256="a" * 64, approval_sha256="b" * 64)
OTHER = StackDigests(profile_sha256="c" * 64, approval_sha256="b" * 64)


def active_state(tmp_path: Path, product: str = "demo") -> StackState:
    return StackState(
        product=product,
        run_id="r1",
        started_at="2026-11-16T10:00:00+00:00",
        not_after="2026-11-16T12:00:00+00:00",
        zap_api_key="k" * 12,
        zap_url="http://127.0.0.1:8080",
        auth_proxy_url="http://127.0.0.1:3128",
        policy_dir=tmp_path / "policy",
        audit_dir=tmp_path / "audit",
        projects=(ComposeProject(name="hdast", workdir=".", files=("compose.yaml",)),),
    )


def make_check(
    tmp_path: Path, bindings: FakeBindingSource, *, active: StackState | None
) -> StackFreshnessCheck:
    states = InMemoryStackState(tmp_path)
    states.state = active
    return StackFreshnessCheck(states, bindings)


def test_ensure_fresh_passa_quando_a_pilha_corresponde(tmp_path: Path) -> None:
    sut = make_check(tmp_path, FakeBindingSource(A, A), active=active_state(tmp_path))

    sut.ensure_fresh("demo")


def test_ensure_fresh_levanta_stack_stale_quando_o_perfil_mudou(tmp_path: Path) -> None:
    sut = make_check(tmp_path, FakeBindingSource(A, OTHER), active=active_state(tmp_path))

    with pytest.raises(StackStale) as caught:
        sut.ensure_fresh("demo")

    assert caught.value.stale_parts == ("profile",)
    assert caught.value.hint is not None
    assert "hdast stack up demo" in caught.value.hint


def test_ensure_fresh_levanta_stack_stale_quando_o_vinculo_esta_ilegivel(tmp_path: Path) -> None:
    bindings = FakeBindingSource(None, A, unreadable=True)
    sut = make_check(tmp_path, bindings, active=active_state(tmp_path))

    with pytest.raises(StackStale) as caught:
        sut.ensure_fresh("demo")

    assert caught.value.stale_parts == ("binding",)


def test_ensure_fresh_nao_decide_sem_pilha_ou_com_pilha_de_outro_produto(tmp_path: Path) -> None:
    stale = FakeBindingSource(A, OTHER)

    make_check(tmp_path, stale, active=None).ensure_fresh("demo")
    make_check(tmp_path, stale, active=active_state(tmp_path, "outro")).ensure_fresh("demo")


def test_ensure_fresh_nao_compara_politica_sem_vinculo(tmp_path: Path) -> None:
    sut = make_check(tmp_path, FakeBindingSource(None, OTHER), active=active_state(tmp_path))

    sut.ensure_fresh("demo")
    inspected = sut.inspect()

    assert inspected is not None
    assert inspected.state == "unbound"


def test_inspect_devolve_none_sem_pilha(tmp_path: Path) -> None:
    assert make_check(tmp_path, FakeBindingSource(A, A), active=None).inspect() is None


def test_inspect_propaga_estado_invalido(tmp_path: Path) -> None:
    class BrokenStates(InMemoryStackState):
        def load(self) -> StackState | None:
            raise ConfigError("estado inválido")

    sut = StackFreshnessCheck(BrokenStates(tmp_path), FakeBindingSource(A, A))

    with pytest.raises(ConfigError):
        sut.inspect()


class RejectingProfiles(InMemoryProfileRepository):
    def load(self, product: str) -> ProductProfile:
        raise ScopeNotApproved("sem aprovação")


def test_fresh_stack_profiles_devolve_o_perfil_quando_a_pilha_esta_fresca(tmp_path: Path) -> None:
    inner = InMemoryProfileRepository()
    inner.add(valid_profile("demo"))
    fresh = make_check(tmp_path, FakeBindingSource(A, A), active=active_state(tmp_path))

    assert FreshStackProfiles(inner, fresh).load("demo").product == "demo"


def test_fresh_stack_profiles_recusa_pilha_velha_mas_a_aprovacao_tem_prioridade(
    tmp_path: Path,
) -> None:
    inner = InMemoryProfileRepository()
    inner.add(valid_profile("demo"))
    stale = make_check(tmp_path, FakeBindingSource(A, OTHER), active=active_state(tmp_path))

    with pytest.raises(StackStale):
        FreshStackProfiles(inner, stale).load("demo")
    with pytest.raises(ScopeNotApproved):
        FreshStackProfiles(RejectingProfiles(), stale).load("demo")
