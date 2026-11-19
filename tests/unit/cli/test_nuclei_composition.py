"""Montagem do `nuclei`: falha fechada sem pilha e ambiente do compose sem segredo de login."""

from pathlib import Path
from typing import cast

import pytest

from harness_dast.application.stack_models import ComposeProject, StackState
from harness_dast.cli.composition import NetworkHandle
from harness_dast.cli.nuclei_composition import _engine_env, build_nuclei
from harness_dast.domain.errors import ConfigError
from harness_dast.observability.logging import SecretRegistry
from tests.fakes.host import FakeHost

RUN_ID = "2026-11-10T12-00-00Z-demo-7f3a"


def _state(tmp_path: Path) -> StackState:
    return StackState(
        product="demo",
        run_id=RUN_ID,
        started_at="2026-11-10T12:00:00+00:00",
        not_after="2026-11-10T13:00:00+00:00",
        zap_api_key="k" * 48,
        zap_url="http://127.0.0.1:8080",
        auth_proxy_url="http://127.0.0.1:3128",
        policy_dir=tmp_path / "p",
        audit_dir=tmp_path / "a",
        nuclei_policy_dir=tmp_path / "pn",
        nuclei_audit_dir=tmp_path / "an",
        projects=(ComposeProject(name="hdast", workdir="/x", files=("compose.yaml",)),),
    )


def test_sem_pilha_gerenciada_a_montagem_falha_fechada_com_a_orientacao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path / "sem-estado"))

    with pytest.raises(ConfigError, match="pilha gerenciada") as raised:
        build_nuclei(tmp_path, SecretRegistry(), cast(NetworkHandle, object()))

    assert raised.value.hint is not None
    assert "hdast stack up" in raised.value.hint


def test_ambiente_do_motor_traz_as_pastas_da_segunda_cerca_e_a_imagem_do_nuclei(
    tmp_path: Path,
) -> None:
    host = FakeHost()

    env = _engine_env(_state(tmp_path), host.stack_images(), {})

    assert env["HDAST_NUCLEI_POLICY_DIR"] == (tmp_path / "pn").as_posix()
    assert env["HDAST_NUCLEI_AUDIT_DIR"] == (tmp_path / "an").as_posix()
    assert env["HDAST_NUCLEI_IMAGE"] == host.images["nuclei"]
    assert "nuclei" in host.requested_services


def test_ambiente_do_motor_nunca_leva_senha_nem_token_de_conta(tmp_path: Path) -> None:
    env = _engine_env(_state(tmp_path), FakeHost().stack_images(), {"MINHA_SENHA": "x"})

    assert "MINHA_SENHA" not in env
    assert not any("TOKEN" in name or "SENHA" in name for name in env)
