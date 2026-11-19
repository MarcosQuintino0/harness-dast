import subprocess
from base64 import b64encode
from collections.abc import Mapping
from pathlib import Path

import pytest

from harness_dast.adapters.docker.compose import (
    BUILD_SECONDS,
    CommandResult,
    DockerComposeCli,
    default_compose_root,
)
from harness_dast.application.stack_models import ComposeProject
from harness_dast.cli.output import build_failure
from harness_dast.domain.errors import ConfigError, ExitCode, ExternalToolError

PROJECT = ComposeProject(
    name="hdast",
    workdir=".",
    files=("compose.yaml",),
    profiles=("lab",),
    services=("zap", "vampi"),
)
SECRET = "chave-zap-muito-secreta"  # noqa: S105


def test_usa_compose_da_raiz_quando_esta_no_clone() -> None:
    root = Path("checkout")
    package = root / "src/harness_dast"
    files = {root / "pyproject.toml", root / "compose.yaml", package / "compose.yaml"}

    assert default_compose_root(package=package, is_file=files.__contains__) == root


def test_usa_compose_do_pacote_quando_instalado() -> None:
    package = Path("venv/lib/site-packages/harness_dast")
    files = {package / "compose.yaml"}

    assert default_compose_root(package=package, is_file=files.__contains__) == package


def test_informa_instalacao_incompleta_quando_compose_falta() -> None:
    with pytest.raises(ConfigError, match=r"Não encontrei o compose\.yaml"):
        default_compose_root(package=Path("site-packages/harness_dast"), is_file=lambda _: False)


class Recorder:
    def __init__(self, result: CommandResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[list[str], dict[str, str], float]] = []

    def __call__(
        self, args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        self.calls.append((args, dict(env), timeout))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def cli(runner: Recorder) -> DockerComposeCli:
    return DockerComposeCli({"PATH": "", "OUTRA": "1"}, runner)


@pytest.fixture(autouse=True)
def fake_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: "docker")


def test_up_monta_o_comando_com_prazo_e_manda_o_segredo_so_no_ambiente() -> None:
    runner = Recorder(CommandResult(0, "", ""))

    cli(runner).up(PROJECT, {"HDAST_ZAP_API_KEY": SECRET}, build=True, timeout_seconds=100)

    args, env, timeout = runner.calls[0]
    assert args[:6] == ["docker", "compose", "-p", "hdast", "-f", "compose.yaml"]
    assert args[-2:] == ["zap", "vampi"]
    assert {"--wait", "--force-recreate", "--build", "--profile"} <= set(args)
    assert SECRET not in " ".join(args)
    assert env["HDAST_ZAP_API_KEY"] == SECRET
    assert env["OUTRA"] == "1"
    assert timeout > 100


def test_up_com_build_ganha_prazo_extra_e_sem_build_fica_como_antes() -> None:
    with_build = Recorder(CommandResult(0, "", ""))
    without = Recorder(CommandResult(0, "", ""))

    cli(with_build).up(PROJECT, {}, build=True, timeout_seconds=100)
    cli(without).up(PROJECT, {}, build=False, timeout_seconds=100)

    assert with_build.calls[0][2] == without.calls[0][2] + BUILD_SECONDS
    assert without.calls[0][2] == 130
    assert "--no-build" in without.calls[0][0]


def test_build_prepara_as_imagens_proprias_sem_subir_servicos() -> None:
    runner = Recorder(CommandResult(0, "", ""))

    cli(runner).build(PROJECT, {}, ("zap", "scope-proxy"))

    assert runner.calls[0][0][-3:] == ["build", "zap", "scope-proxy"]
    assert runner.calls[0][2] == BUILD_SECONDS


def test_falha_do_compose_vira_erro_de_ferramenta_sem_vazar_o_segredo() -> None:
    runner = Recorder(CommandResult(1, "", f"erro com {SECRET} dentro"))

    with pytest.raises(ExternalToolError) as error:
        cli(runner).down(PROJECT, {"HDAST_ZAP_API_KEY": SECRET}, timeout_seconds=10)

    assert SECRET not in error.value.message
    assert error.value.hint


def _call_operation(compose: DockerComposeCli, operation: str) -> None:
    if operation == "up":
        compose.up(PROJECT, {}, build=False, timeout_seconds=10)
    elif operation == "down":
        compose.down(PROJECT, {}, timeout_seconds=10)
    else:
        compose.status(PROJECT, {})


@pytest.mark.parametrize("operation", ["up", "down", "status"])
@pytest.mark.parametrize("secret", ["Q7", "senha-sintetica-43"])
@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_falha_omite_saida_com_credencial_herdada_e_codificada(
    operation: str, secret: str, stream: str
) -> None:
    encoded = b64encode(secret.encode()).decode()
    raw = f"credencial={secret} codificada={encoded} marcador-de-erro"
    result = CommandResult(42, raw if stream == "stdout" else "", raw if stream == "stderr" else "")
    runner = Recorder(result)
    compose = DockerComposeCli({"PATH": "", "CRAPI_DB_PASSWORD": secret}, runner)

    with pytest.raises(ExternalToolError) as error:
        _call_operation(compose, operation)

    assert runner.calls[0][1]["CRAPI_DB_PASSWORD"] == secret
    envelope = build_failure(error.value).model_dump_json()
    assert error.value.exit_code == ExitCode.EXTERNAL_TOOL
    assert "42" in error.value.message
    assert secret not in envelope
    assert encoded not in envelope
    assert "marcador-de-erro" not in envelope


def test_down_remove_volumes_somente_quando_projeto_os_declara_descartaveis() -> None:
    runner = Recorder(CommandResult(0, "", ""))
    cli(runner).down(PROJECT.model_copy(update={"remove_volumes": True}), {}, timeout_seconds=10)
    assert "--volumes" in runner.calls[0][0]


def test_prazo_estourado_vira_erro_de_ferramenta_com_orientacao() -> None:
    runner = Recorder(subprocess.TimeoutExpired("docker", 10))

    with pytest.raises(ExternalToolError, match="não terminou"):
        cli(runner).up(PROJECT, {}, build=False, timeout_seconds=10)


def test_docker_ausente_vira_erro_de_ferramenta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)

    with pytest.raises(ExternalToolError, match="não foi encontrado"):
        cli(Recorder(CommandResult(0, "", ""))).status(PROJECT, {})


def test_status_le_um_objeto_por_linha_e_tambem_lista_json() -> None:
    line = '{"Service":"zap","State":"running","Health":"healthy"}'
    per_line = cli(Recorder(CommandResult(0, line + "\n" + line, ""))).status(PROJECT, {})
    as_list = cli(Recorder(CommandResult(0, f"[{line}]", ""))).status(PROJECT, {})

    assert len(per_line) == 2
    assert as_list[0].service == "zap"
    assert as_list[0].health == "healthy"


def test_status_vazio_e_saida_ilegivel() -> None:
    assert cli(Recorder(CommandResult(0, "", ""))).status(PROJECT, {}) == ()
    with pytest.raises(ExternalToolError, match="não é JSON"):
        cli(Recorder(CommandResult(0, "isto nao e json", ""))).status(PROJECT, {})
