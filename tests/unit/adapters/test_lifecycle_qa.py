"""Confirmação de ciclo sem Docker nem valores de ambiente reais."""

import json
import subprocess
from pathlib import Path

import pytest

from tests.integration.lab_support import CliResult
from tests.integration.performance_lifecycle_support import (
    Lifecycle,
    LifecycleError,
    docker_metadata,
    snapshot,
)

_ID = "a" * 64
_SERVICES = ("zap", "zap-gateway", "scope-proxy", "proxy-gateway", "vampi")


class FakeRunner:
    def __init__(self) -> None:
        self.rows: dict[str, str] = {"hdast": "", "hdast-pilotrun": ""}
        self.exit_code = 0
        self.timeout = False

    def __call__(self, project: str) -> subprocess.CompletedProcess[str]:
        if self.timeout:
            raise subprocess.TimeoutExpired("docker", 30)
        return subprocess.CompletedProcess([], self.exit_code, self.rows[project], "nao-publicar")


class FakeCli:
    def __init__(self, code: int) -> None:
        self.code = code

    def run(self, *args: str, timeout: int = 420) -> CliResult:
        return CliResult(self.code, {}, "nao-publicar", "nao-publicar")


def _rows() -> str:
    return "\n".join(
        f"{index:064x}|{service}|running" for index, service in enumerate(_SERVICES, 1)
    )


def test_ciclo_salva_apenas_hashes_e_exige_vazio_ao_final(tmp_path: Path) -> None:
    fake = FakeRunner()
    lifecycle = Lifecycle(tmp_path, "rodada", "vampi", fake)
    lifecycle.before_up()
    fake.rows["hdast"] = _rows()
    lifecycle.after_up()
    fake.rows["hdast"] = ""
    lifecycle.down(FakeCli(0))
    saved = json.loads(lifecycle.path.read_text(encoding="utf-8"))
    assert saved["status"] == "ciclo_containers_confirmado"
    assert len(saved["phases"]["after_up"]["containers"]) == 5
    assert _ID not in lifecycle.path.read_text(encoding="utf-8")
    assert f"{1:064x}" not in lifecycle.path.read_text(encoding="utf-8")
    assert "nao-publicar" not in lifecycle.path.read_text(encoding="utf-8")


def test_antes_de_subir_recusa_containers_residuais(tmp_path: Path) -> None:
    fake = FakeRunner()
    fake.rows["hdast"] = f"{_ID}|zap|running"
    lifecycle = Lifecycle(tmp_path, "rodada", "vampi", fake)
    with pytest.raises(LifecycleError, match="before_up_unexpected_containers"):
        lifecycle.before_up()
    assert json.loads(lifecycle.path.read_text(encoding="utf-8"))["status"] == "inconclusivo"


@pytest.mark.parametrize("failure", ["bad_line", "docker_failed", "docker_timeout"])
def test_metadata_invalida_ou_indisponivel_nao_e_vazio(failure: str) -> None:
    fake = FakeRunner()
    if failure == "bad_line":
        fake.rows["hdast"] = "invalido dados nao-publicar"
    elif failure == "docker_failed":
        fake.exit_code = 1
    else:
        fake.timeout = True
    with pytest.raises(LifecycleError):
        snapshot(fake)


@pytest.mark.parametrize("failure", ["missing", "extra", "stopped"])
def test_subida_exige_servicos_exatos_em_execucao(tmp_path: Path, failure: str) -> None:
    fake = FakeRunner()
    lifecycle = Lifecycle(tmp_path, "rodada", "vampi", fake)
    lifecycle.before_up()
    rows = _rows().splitlines()
    if failure == "missing":
        rows.pop()
    elif failure == "extra":
        rows.append(f"{_ID}|outro|running")
    else:
        rows[0] = rows[0].replace("running", "exited")
    fake.rows["hdast"] = "\n".join(rows)
    with pytest.raises(LifecycleError, match="after_up_unexpected_containers"):
        lifecycle.after_up()


def test_down_com_erro_nao_se_torna_sucesso_mesmo_sem_residuo(tmp_path: Path) -> None:
    fake = FakeRunner()
    lifecycle = Lifecycle(tmp_path, "rodada", "vampi", fake)
    lifecycle.before_up()
    with pytest.raises(LifecycleError, match="down_failed"):
        lifecycle.down(FakeCli(1))
    saved = json.loads(lifecycle.path.read_text(encoding="utf-8"))
    assert saved["status"] == "inconclusivo"
    assert saved["phases"]["after_down"]["status"] == "ok"


def test_down_com_residuo_bloqueia_proximo_cenario(tmp_path: Path) -> None:
    fake = FakeRunner()
    lifecycle = Lifecycle(tmp_path, "rodada", "vampi", fake)
    lifecycle.before_up()
    fake.rows["hdast"] = f"{_ID}|zap|exited"
    with pytest.raises(LifecycleError, match="after_down_unexpected_containers"):
        lifecycle.down(FakeCli(0))


def test_id_repetido_na_metadata_nao_vira_comprovacao() -> None:
    fake = FakeRunner()
    fake.rows["hdast"] = f"{_ID}|zap|running\n{_ID}|vampi|running"
    with pytest.raises(LifecycleError, match="duplicate_id"):
        snapshot(fake)


def test_clinica_exige_pilot_em_projeto_anexo(tmp_path: Path) -> None:
    fake = FakeRunner()
    lifecycle = Lifecycle(tmp_path, "rodada", "clinica-piloto", fake)
    lifecycle.before_up()
    fake.rows["hdast"] = "\n".join(_rows().splitlines()[:-1])
    fake.rows["hdast-pilotrun"] = f"{_ID}|pilot|running"
    lifecycle.after_up()
    saved = json.loads(lifecycle.path.read_text(encoding="utf-8"))
    assert saved["phases"]["after_up"]["status"] == "ok"


def test_timeout_no_down_registra_inspecao_posterior(tmp_path: Path) -> None:
    class TimeoutCli(FakeCli):
        def run(self, *args: str, timeout: int = 420) -> CliResult:
            raise subprocess.TimeoutExpired("hdast", timeout)

    fake = FakeRunner()
    lifecycle = Lifecycle(tmp_path, "rodada", "vampi", fake)
    lifecycle.before_up()
    with pytest.raises(LifecycleError, match="down_unavailable"):
        lifecycle.down(TimeoutCli(0))
    saved = json.loads(lifecycle.path.read_text(encoding="utf-8"))
    assert saved["phases"]["after_down"]["status"] == "ok"
    assert saved["status"] == "inconclusivo"


def test_encerramento_sem_subida_observada_nao_confirma_ciclo(tmp_path: Path) -> None:
    lifecycle = Lifecycle(tmp_path, "rodada", "vampi", FakeRunner())
    lifecycle.before_up()
    lifecycle.down(FakeCli(0))
    saved = json.loads(lifecycle.path.read_text(encoding="utf-8"))
    assert saved["status"] == "inconclusivo"


def test_ledger_antigo_nao_e_sobrescrito(tmp_path: Path) -> None:
    lifecycle = Lifecycle(tmp_path, "rodada", "vampi", FakeRunner())
    original = lifecycle.path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        Lifecycle(tmp_path, "rodada", "vampi", FakeRunner())
    assert lifecycle.path.read_text(encoding="utf-8") == original


def test_consulta_externa_usa_somente_metadata_restrita(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs["timeout"] == 30
        assert kwargs.get("shell") is not True
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("shutil.which", lambda _: "docker")
    monkeypatch.setattr("subprocess.run", fake_run)
    result = docker_metadata("hdast")
    assert result.returncode == 0
    assert calls[0][1:6] == [
        "ps",
        "-a",
        "--no-trunc",
        "--filter",
        "label=com.docker.compose.project=hdast",
    ]
    assert "{{.ID}}" in calls[0][-1]
    assert "{{.State}}" in calls[0][-1]


def test_consulta_recusa_projeto_fora_da_lista() -> None:
    with pytest.raises(ValueError, match="projeto inesperado"):
        docker_metadata("outro-projeto")
