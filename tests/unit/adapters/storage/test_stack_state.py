import stat
import sys
from pathlib import Path

import pytest

from harness_dast.adapters.storage.stack_state import FileStackStateStore, default_state_dir
from harness_dast.application.stack_models import ComposeProject, StackState
from harness_dast.domain.errors import ConfigError

RUN_ID = "2026-11-10T12-00-00Z-demo-7f3a"


def make_state(tmp_path: Path) -> StackState:
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
        projects=(ComposeProject(name="hdast", workdir="/x", files=("compose.yaml",)),),
        target_env={"PILOT_ADMIN_PASSWORD": "s3gredo"},
    )


def test_load_devolve_none_quando_nao_ha_arquivo(tmp_path: Path) -> None:
    assert FileStackStateStore(tmp_path).load() is None


def test_save_e_load_fazem_ida_e_volta(tmp_path: Path) -> None:
    store = FileStackStateStore(tmp_path / "estado")
    state = make_state(tmp_path)

    store.save(state)

    assert store.load() == state


@pytest.mark.skipif(sys.platform == "win32", reason="modo POSIX")
def test_arquivo_de_estado_so_e_legivel_pela_pessoa_usuaria(tmp_path: Path) -> None:
    store = FileStackStateStore(tmp_path / "estado")

    store.save(make_state(tmp_path))

    assert stat.S_IMODE(store.location().stat().st_mode) == 0o600


def test_arquivo_invalido_vira_config_error_sem_repetir_o_conteudo(tmp_path: Path) -> None:
    (tmp_path / "stack.json").write_text('{"zap_api_key": "segredo-vazado"}', encoding="utf-8")

    with pytest.raises(ConfigError) as error:
        FileStackStateStore(tmp_path).load()

    assert "segredo-vazado" not in error.value.message


def test_clear_apaga_o_estado_e_nao_falha_sem_arquivo(tmp_path: Path) -> None:
    store = FileStackStateStore(tmp_path)
    store.save(make_state(tmp_path))

    store.clear()
    store.clear()

    assert store.load() is None


def test_directories_for_cria_pastas_separadas_por_pilha(tmp_path: Path) -> None:
    store = FileStackStateStore(tmp_path)

    first = store.directories_for(RUN_ID)
    second = store.directories_for("2026-11-10T12-05-00Z-demo-aaaa")

    assert first.policy_dir.is_dir()
    assert first.audit_dir.is_dir()
    assert first.policy_dir != second.policy_dir


def test_directories_for_recusa_run_id_que_escapa_da_pasta(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="formato"):
        FileStackStateStore(tmp_path).directories_for("../fora")


@pytest.mark.parametrize(
    ("environ", "windows", "expected"),
    [
        ({"HDAST_STATE_DIR": "/x/estado"}, False, Path("/x/estado")),
        ({"LOCALAPPDATA": "C:/L"}, True, Path("C:/L/hdast")),
        ({"XDG_STATE_HOME": "/s"}, False, Path("/s/hdast")),
    ],
)
def test_default_state_dir_segue_a_precedencia(
    environ: dict[str, str], windows: bool, expected: Path
) -> None:
    assert default_state_dir(environ, windows=windows) == expected
