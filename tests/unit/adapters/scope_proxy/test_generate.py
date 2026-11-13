"""A política gerada precisa ser aceita pelo validador do contêiner e nunca ser mais larga."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from harness_dast.adapters.scope_proxy.generate import (
    POLICY_FILE_NAME,
    FileProxyPolicyStore,
    build_proxy_policy,
)
from harness_dast.adapters.scope_proxy.policy import load_policy
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run import RunId
from tests.fakes.profile_data import valid_profile, valid_profile_data

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
RUN_ID = RunId.create(started_at=NOW, product="demo", suffix="7f3a")
NOT_AFTER = datetime(2026, 11, 10, 13, 0, tzinfo=UTC)


def test_politica_gravada_e_lida_de_volta_pelo_validador_do_proxy(tmp_path: Path) -> None:
    profile = valid_profile()

    path = FileProxyPolicyStore().publish(profile, RUN_ID, NOT_AFTER, tmp_path)

    loaded = load_policy(path)
    assert path.name == POLICY_FILE_NAME
    assert loaded.run_id == RUN_ID.value
    assert loaded.scope == profile.scope.to_scope()
    assert loaded.limits == profile.limits
    assert loaded.not_after == NOT_AFTER
    assert loaded.tls_verify_upstream is True


def test_politica_tem_as_mesmas_regras_e_negacoes_do_perfil() -> None:
    profile = valid_profile()

    policy = build_proxy_policy(profile, RUN_ID, NOT_AFTER)

    assert policy.scope.allow == profile.scope.allow
    assert policy.scope.deny_paths == profile.scope.deny_paths


def test_verificacao_de_tls_so_e_relaxada_quando_o_perfil_pede_e_o_host_e_local() -> None:
    data = valid_profile_data()
    data["environment"]["base_url"] = "http://lab-api:8080"
    data["environment"]["verify_tls"] = False
    data["scope"]["allow"] = [
        {
            "host": "lab-api",
            "scheme": "http",
            "port": 8080,
            "allow_local": True,
            "paths": ["/api/**"],
            "methods": ["GET", "POST"],
        }
    ]
    relaxed = ProductProfile.from_data(data)

    assert build_proxy_policy(relaxed, RUN_ID, NOT_AFTER).tls_verify_upstream is False
    assert build_proxy_policy(valid_profile(), RUN_ID, NOT_AFTER).tls_verify_upstream is True


def test_trigger_kill_diz_que_ja_existia_na_segunda_vez(tmp_path: Path) -> None:
    store = FileProxyPolicyStore()

    first = store.trigger_kill(tmp_path)
    second = store.trigger_kill(tmp_path)

    assert (first, second) == (True, False)
    assert store.kill_active(tmp_path) is True


def test_trigger_kill_falha_alto_quando_a_pasta_nao_existe(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="não existe"):
        FileProxyPolicyStore().trigger_kill(tmp_path / "nao-existe")
