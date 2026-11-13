import json
from pathlib import Path

import pytest

from harness_dast.adapters.storage.stack_state import FileStackStateStore
from harness_dast.application.stack_models import ComposeProject, StackState
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.stack_composition import layered_environ, load_effective_settings

KEY = "chave-do-estado-123456"


def save_state(directory: Path) -> None:
    FileStackStateStore(directory).save(
        StackState(
            product="demo",
            run_id="2026-11-10T12-00-00Z-demo-7f3a",
            started_at="2026-11-10T12:00:00+00:00",
            not_after="2026-11-10T13:00:00+00:00",
            zap_api_key=KEY,
            zap_url="http://127.0.0.1:18080",
            auth_proxy_url="http://127.0.0.1:13128",
            policy_dir=directory / "p",
            audit_dir=directory / "a",
            projects=(ComposeProject(name="hdast", workdir="/x", files=("compose.yaml",)),),
            target_env={"PILOT_ADMIN_PASSWORD": "do-estado", "PILOT_X": "do-estado"},
        )
    )


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    for name in ("HDAST_ZAP_BASE_URL", "HDAST_ZAP_API_KEY", "HDAST_AUTH_PROXY_URL"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_sem_pilha_gerenciada_a_configuracao_nao_muda(state_dir: Path) -> None:
    settings = load_effective_settings()

    assert settings.zap_base_url == "http://127.0.0.1:8080"
    assert settings.zap_api_key is None
    assert settings.auth_proxy_url is None


def test_estado_preenche_o_que_o_ambiente_nao_definiu(state_dir: Path) -> None:
    save_state(state_dir)

    settings = load_effective_settings()

    assert settings.zap_base_url == "http://127.0.0.1:18080"
    assert settings.auth_proxy_url == "http://127.0.0.1:13128"
    assert settings.zap_api_key is not None
    assert settings.zap_api_key.get_secret_value() == KEY
    assert settings.effective_zap_proxy_url == "http://127.0.0.1:18080"


def test_variavel_de_ambiente_sempre_vence_o_estado(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_state(state_dir)
    monkeypatch.setenv("HDAST_AUTH_PROXY_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("HDAST_ZAP_API_KEY", "chave-do-ambiente")

    settings = load_effective_settings()

    assert settings.auth_proxy_url == "http://127.0.0.1:9999"
    assert settings.zap_api_key is not None
    assert settings.zap_api_key.get_secret_value() == "chave-do-ambiente"


def test_ambiente_em_camadas_deixa_o_processo_vencer_as_senhas_do_estado(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_state(state_dir)
    monkeypatch.setenv("PILOT_ADMIN_PASSWORD", "do-processo")

    merged = layered_environ()

    assert merged["PILOT_ADMIN_PASSWORD"] == "do-processo"  # noqa: S105
    assert merged["PILOT_X"] == "do-estado"


def test_stack_status_sem_pilha_sai_com_zero_e_envelope_valido(
    state_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_app(build_app(), ["--json", "stack", "status"])

    envelope = json.loads(capsys.readouterr().out)
    assert code == 0
    assert envelope["ok"] is True
    assert envelope["data"]["managed"] is False


def test_stack_status_nao_imprime_a_chave_nem_as_senhas(
    state_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    save_state(state_dir)
    monkeypatch.setattr(
        "harness_dast.cli.stack_composition.DockerComposeCli.status",
        lambda *_a, **_k: (),
    )

    run_app(build_app(), ["--json", "stack", "status"])

    out = capsys.readouterr().out
    assert KEY not in out
    assert "do-estado" not in out
