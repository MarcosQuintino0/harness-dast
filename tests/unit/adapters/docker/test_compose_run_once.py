"""Execução única do Nuclei: entrada fechada, prazo com morte do contêiner e saída repassada."""

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.docker.compose import (
    KILL_SECONDS,
    CommandResult,
    DockerComposeCli,
    run_subprocess,
)
from harness_dast.application.stack_models import ComposeProject
from harness_dast.domain.errors import ConfigError, ExternalToolError

PROJECT = ComposeProject(name="hdast-x", workdir=".", files=("compose.yaml",), profiles=("nuclei",))
NAME = "hdast-nuclei-once"
SECRET = "segredo-do-ambiente"  # noqa: S105


class Sequence:
    """Devolve, em ordem, um resultado ou levanta a exceção programada para cada chamada."""

    def __init__(self, *steps: CommandResult | Exception) -> None:
        self._steps = list(steps)
        self.calls: list[tuple[list[str], dict[str, str], float]] = []

    def __call__(
        self, args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        self.calls.append((args, dict(env), timeout))
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture(autouse=True)
def fake_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: "docker")


def _cli(runner: Sequence) -> DockerComposeCli:
    return DockerComposeCli({"PATH": ""}, runner)


def _run(runner: Sequence, **extra: Any) -> Any:
    return _cli(runner).run_once(
        PROJECT,
        {"HDAST_ZAP_API_KEY": SECRET},
        "nuclei",
        ("-ni", "-duc"),
        container_name=NAME,
        timeout_seconds=90,
        **extra,
    )


def test_run_once_monta_run_rm_sem_terminal_nem_dependencias_com_nome_fixo() -> None:
    runner = Sequence(CommandResult(0, "linha\n", ""))

    result = _run(runner, mounts=("/dados/lista.txt:/in/lista.txt:ro",))

    args, env, timeout = runner.calls[0]
    assert args[:6] == ["docker", "compose", "-p", "hdast-x", "-f", "compose.yaml"]
    run = args.index("run")
    assert args[run : run + 6] == ["run", "--rm", "-T", "--no-deps", "--name", NAME]
    assert args[-5:] == ["-v", "/dados/lista.txt:/in/lista.txt:ro", "nuclei", "-ni", "-duc"]
    assert timeout == 90
    assert env["HDAST_ZAP_API_KEY"] == SECRET
    assert SECRET not in " ".join(args)
    assert (result.exit_code, result.stdout) == (0, "linha\n")


def test_run_once_repassa_o_codigo_de_saida_do_conteiner() -> None:
    runner = Sequence(CommandResult(7, "parcial", "erro"))

    result = _run(runner)

    assert result.exit_code == 7
    assert result.stdout == "parcial"
    assert len(runner.calls) == 1


def test_run_once_estourar_o_prazo_mata_e_remove_o_conteiner_pelo_nome() -> None:
    runner = Sequence(subprocess.TimeoutExpired("docker", 90), CommandResult(0, NAME, ""))

    with pytest.raises(ExternalToolError, match="passou do prazo de 90 s"):
        _run(runner)

    kill, _, kill_timeout = runner.calls[1]
    assert kill == ["docker", "rm", "-f", NAME]
    assert kill_timeout == KILL_SECONDS


def test_run_once_prazo_com_conteiner_que_ja_saiu_ainda_reporta_o_prazo() -> None:
    gone = CommandResult(1, "", f"Error response from daemon: No such container: {NAME}")
    runner = Sequence(subprocess.TimeoutExpired("docker", 90), gone)

    with pytest.raises(ExternalToolError, match="foi encerrado"):
        _run(runner)


def test_run_once_prazo_sem_conseguir_matar_orienta_a_remover_na_mao() -> None:
    runner = Sequence(
        subprocess.TimeoutExpired("docker", 90), CommandResult(1, "", "daemon ocupado")
    )

    with pytest.raises(ExternalToolError) as error:
        _run(runner)

    assert "não pôde ser encerrado" in error.value.message
    assert f"docker rm -f {NAME}" in (error.value.hint or "")


def test_run_once_prazo_e_morte_que_tambem_estoura_orienta_a_remover_na_mao() -> None:
    runner = Sequence(
        subprocess.TimeoutExpired("docker", 90), subprocess.TimeoutExpired("docker", 30)
    )

    with pytest.raises(ExternalToolError) as error:
        _run(runner)

    assert f"docker rm -f {NAME}" in (error.value.hint or "")


def test_run_once_docker_que_nao_executa_vira_erro_de_ferramenta() -> None:
    runner = Sequence(OSError("sem docker"))

    with pytest.raises(ExternalToolError, match="executar o docker"):
        _run(runner)


def test_run_once_sem_docker_no_path_orienta_a_instalar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)

    with pytest.raises(ExternalToolError, match="docker não foi encontrado"):
        _run(Sequence())


@pytest.mark.parametrize("name", ["", "Maiuscula", "-comeca-com-hifen", "tem espaco", "a" * 64])
def test_run_once_recusa_nome_de_conteiner_invalido(name: str) -> None:
    runner = Sequence()

    with pytest.raises(ConfigError, match="Nome de contêiner"):
        _cli(runner).run_once(PROJECT, {}, "nuclei", (), container_name=name, timeout_seconds=10)

    assert runner.calls == []


@pytest.mark.parametrize("mount", ["/a:/b", "/a:/b:rw", "-v:/b:ro", "/a:/b:ro\n"])
def test_run_once_recusa_montagem_que_nao_e_somente_leitura(mount: str) -> None:
    runner = Sequence()

    with pytest.raises(ConfigError, match="só leitura"):
        _run(runner, mounts=(mount,))

    assert runner.calls == []


def test_processo_do_docker_roda_com_a_entrada_padrao_em_dev_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_subprocess(["docker", "compose", "run"], {}, Path("."), 5)

    assert seen["stdin"] is subprocess.DEVNULL
    assert seen["timeout"] == 5


def test_kill_container_remove_o_conteiner_pelo_nome_sem_levantar_prazo() -> None:
    runner = Sequence(CommandResult(0, NAME, ""))

    _cli(runner).kill_container(PROJECT, {"HDAST_ZAP_API_KEY": SECRET}, NAME)

    args, env, timeout = runner.calls[0]
    assert args == ["docker", "rm", "-f", NAME]
    assert env["HDAST_ZAP_API_KEY"] == SECRET
    assert timeout == KILL_SECONDS


def test_kill_container_que_ja_saiu_conta_como_encerrado() -> None:
    gone = CommandResult(1, "", f"Error response from daemon: No such container: {NAME}")

    _cli(Sequence(gone)).kill_container(PROJECT, {}, NAME)


def test_kill_container_que_nao_morre_orienta_a_remover_na_mao() -> None:
    runner = Sequence(CommandResult(1, "", "daemon ocupado"))

    with pytest.raises(ExternalToolError) as error:
        _cli(runner).kill_container(PROJECT, {}, NAME)

    assert f"docker rm -f {NAME}" in (error.value.hint or "")


@pytest.mark.parametrize("name", ["", "Maiuscula", "-hifen", "a b"])
def test_kill_container_recusa_nome_invalido_sem_chamar_o_docker(name: str) -> None:
    runner = Sequence()

    with pytest.raises(ConfigError, match="Nome de contêiner"):
        _cli(runner).kill_container(PROJECT, {}, name)

    assert runner.calls == []
