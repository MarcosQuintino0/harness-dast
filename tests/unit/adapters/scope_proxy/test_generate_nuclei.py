"""A política da segunda cerca: a derivada do perfil ou a que nega tudo (ADR 0122)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from harness_dast.adapters.scope_proxy.generate import (
    FileProxyPolicyStore,
    build_deny_all_policy,
)
from harness_dast.adapters.scope_proxy.policy import deadline_of, load_policy
from harness_dast.domain.nuclei_scope import nuclei_scope_for
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.proxy_deadline import stack_validity_minutes
from harness_dast.domain.run import RunId
from harness_dast.domain.scope import OutboundRequest, ScopeGuard
from tests.fakes.profile_data import valid_profile, valid_profile_data

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
RUN_ID = RunId.create(started_at=NOW, product="demo", suffix="7f3a")
NOT_AFTER = datetime(2026, 11, 10, 13, 0, tzinfo=UTC)
HOST = "api.hml.acme-teste.net.br"
ROOT = Path(__file__).resolve().parents[4]


def _nuclei_profile(**extra_checks: bool) -> ProductProfile:
    data = valid_profile_data()
    data["extra_checks"] = {"nuclei": True, **extra_checks}
    return ProductProfile.from_data(data)


def _allowed(guard: ScopeGuard, method: str, url: str) -> bool:
    return guard.evaluate(OutboundRequest(method=method, url=url)).verdict == "allowed"


def test_politica_do_nuclei_sem_o_motor_ligado_nega_todo_pedido(tmp_path: Path) -> None:
    path = FileProxyPolicyStore().publish_nuclei(valid_profile(), RUN_ID, NOT_AFTER, tmp_path, None)

    policy = load_policy(path)
    guard = ScopeGuard(policy.scope)
    for method in ("GET", "POST", "OPTIONS", "DELETE"):
        for url in (f"https://{HOST}/api/x", f"https://{HOST}/", "https://deny-all.example/"):
            assert not _allowed(guard, method, url)
    assert deadline_of(policy, NOT_AFTER) < NOT_AFTER
    assert policy.stack_minutes == 1
    assert policy.run_id == RUN_ID.value


def test_politica_que_nega_tudo_nao_cita_nenhuma_origem_do_produto() -> None:
    policy = build_deny_all_policy(valid_profile(), RUN_ID)

    assert [rule.host for rule in policy.scope.allow] == ["deny-all.example"]
    assert policy.scope.deny_paths == ("/**",)
    assert policy.limits == valid_profile().limits


def test_politica_do_nuclei_com_o_motor_usa_o_escopo_derivado_e_o_prazo_da_pilha(
    tmp_path: Path,
) -> None:
    profile = _nuclei_profile(nuclei_wide_paths=True)
    nuclei = nuclei_scope_for(profile)
    assert nuclei is not None

    path = FileProxyPolicyStore().publish_nuclei(profile, RUN_ID, NOT_AFTER, tmp_path, nuclei)

    policy = load_policy(path)
    assert policy.scope == nuclei.scope
    assert policy.path_mode == "wide"
    assert policy.not_after == NOT_AFTER
    assert policy.limits == profile.limits
    assert policy.stack_minutes == stack_validity_minutes(profile)
    assert policy.scope.deny_paths == profile.scope.to_scope().deny_paths


def test_politica_do_nuclei_estrita_mantem_o_modo_do_perfil(tmp_path: Path) -> None:
    profile = _nuclei_profile()
    nuclei = nuclei_scope_for(profile)
    assert nuclei is not None

    policy = load_policy(
        FileProxyPolicyStore().publish_nuclei(profile, RUN_ID, NOT_AFTER, tmp_path, nuclei)
    )

    assert policy.path_mode == "strict"


@pytest.mark.parametrize("folder", ["docker/scope-proxy", "src/harness_dast/compose_data"])
def test_politica_padrao_da_pasta_do_nuclei_nega_tudo_e_ja_venceu(folder: str) -> None:
    policy = load_policy(ROOT / folder / "policy-nuclei" / "policy.json")

    guard = ScopeGuard(policy.scope)
    assert policy.scope.deny_paths == ("/**",)
    assert deadline_of(policy, datetime.now(UTC)) < datetime.now(UTC)
    for url in ("https://deny-all.example/", "https://deny-all.example/a/b"):
        assert not _allowed(guard, "OPTIONS", url)
