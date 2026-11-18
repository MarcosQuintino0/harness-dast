"""Contrato da demo com terminal, máquina e processos filhos falsos."""

import json
import tempfile
from collections.abc import Mapping
from pathlib import Path

import pytest
import typer

from harness_dast.adapters.docker.compose import CommandResult
from harness_dast.application.stack_models import StackProjectSuffix
from harness_dast.cli import demo_runtime
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import demo
from harness_dast.cli.output import build_failure, build_success
from harness_dast.domain.errors import ExitCode, ExternalToolError
from tests.fakes.host import FakeHost

pytestmark = pytest.mark.contract

RUN_ID = "2026-11-18T12-00-00Z-vampi-abcd"
IMAGE = "erev0s/vampi:local"


class FakeDemoCli:
    """Mantém o estado da pilha e grava o relatório quando o run simulado avança."""

    def __init__(self) -> None:
        self.environment: dict[str, str] = {}
        self.stack_running = False
        self.up_fails = False
        self.run_fails = False
        self.interrupt = False
        self.findings = False
        self.down_fails = False
        self.approval_present_at_start = False

    def __call__(
        self, args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        self.environment = dict(env)
        state = Path(env["HDAST_STATE_DIR"])
        if args[5:7] == ["stack", "up"]:
            self.approval_present_at_start = (state / "approvals" / "vampi.json").is_file()
            self.stack_running = True
            if self.up_fails:
                return self._failed("A subida falhou.")
            return CommandResult(0, build_success({}).model_dump_json(), "")
        if args[5:7] == ["stack", "down"]:
            if self.down_fails:
                return self._failed("A desmontagem falhou.")
            self.stack_running = False
            return CommandResult(0, build_success({}).model_dump_json(), "")
        assert args[5:] == ["run", "vampi", "--max-minutes", str(demo_runtime.DEMO_MINUTES)]
        if self.interrupt:
            raise KeyboardInterrupt
        if self.run_fails:
            return self._failed("O run falhou.")
        report = Path(env["HDAST_RUNS_DIR"]) / RUN_ID / "report.html"
        report.parent.mkdir(parents=True)
        report.write_text("<html>Relatório simulado</html>", encoding="utf-8")
        envelope = build_success({"artifacts": {"report.html": "report.html"}}, RUN_ID)
        return CommandResult(
            ExitCode.FINDINGS if self.findings else 0, envelope.model_dump_json(), ""
        )

    @staticmethod
    def _failed(message: str) -> CommandResult:
        error = ExternalToolError(message)
        return CommandResult(error.exit_code, build_failure(error).model_dump_json(), "")


class FakeDemo:
    """Raiz reservada pelo alocador falso e respostas digitadas pela pessoa simulada."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.root = tmp_path / "sessao_com_espacos" / "demo_1234"
        self.cli = FakeDemoCli()
        self.host = FakeHost()
        self.host.images["vampi"] = IMAGE
        self.host.present.add(IMAGE)
        self.answer = "demo"
        self.prompts: list[str] = []
        self.browser_offered = False
        monkeypatch.setattr(demo, "is_interactive", lambda: True)
        monkeypatch.setattr(demo_runtime, "SystemHost", lambda _env: self.host)
        monkeypatch.setattr(demo_runtime, "run_subprocess", self.cli)
        monkeypatch.setattr(tempfile, "mkdtemp", self._new_directory)
        monkeypatch.setattr(typer, "prompt", self._type)
        monkeypatch.setattr(typer, "confirm", self._decline_browser)

    def _new_directory(self, *, prefix: str) -> str:
        self.root.mkdir(parents=True)
        return str(self.root)

    def _type(self, text: str, **options: object) -> str:
        self.prompts.append(text)
        return self.answer

    def _decline_browser(self, text: str, **options: object) -> bool:
        self.browser_offered = True
        return False


@pytest.fixture
def lab(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeDemo:
    return FakeDemo(monkeypatch, tmp_path)


def test_demo_recusa_quando_nao_ha_terminal(
    lab: FakeDemo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(demo, "is_interactive", lambda: False)

    code = run_app(build_app(), ["demo"])

    assert code == ExitCode.USAGE
    assert "terminal interativo" in capsys.readouterr().err
    assert lab.host.docker_calls == 0


@pytest.mark.parametrize("args", [["--json", "demo"], ["demo", "--json", "--keep"]])
def test_demo_emite_envelope_de_recusa_quando_json_mesmo_com_tty(
    lab: FakeDemo, capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    code = run_app(build_app(), args)

    captured = capsys.readouterr()
    envelope = json.loads(captured.out)
    assert code == ExitCode.USAGE
    assert envelope["schema_version"] == 1
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert lab.prompts == []


@pytest.mark.parametrize("args", [["https://example.invalid"], ["--products-dir", "outro"]])
def test_demo_recusa_quando_tentam_informar_outro_alvo(lab: FakeDemo, args: list[str]) -> None:
    code = run_app(build_app(), ["--json", "demo", *args])

    assert code == ExitCode.USAGE
    assert lab.host.docker_calls == 0


def test_demo_para_antes_da_aprovacao_quando_docker_esta_ausente(
    lab: FakeDemo, capsys: pytest.CaptureFixture[str]
) -> None:
    lab.host.docker_error = ExternalToolError("O Docker não foi encontrado.")

    code = run_app(build_app(), ["demo"])

    assert code == ExitCode.PREFLIGHT
    assert "docs/comecar/docker.md" in capsys.readouterr().err
    assert lab.prompts == []
    assert not lab.root.exists()


@pytest.mark.parametrize("precondition", ["image", "port"])
def test_demo_recusa_quando_falta_imagem_auxiliar_ou_porta_livre(
    lab: FakeDemo, precondition: str
) -> None:
    if precondition == "image":
        lab.host.present.remove(IMAGE)
    else:
        lab.host.busy_ports.add(8080)

    code = run_app(build_app(), ["demo"])

    assert code == ExitCode.PREFLIGHT
    assert lab.prompts == []


def test_demo_cancela_quando_o_nome_digitado_e_outro(
    lab: FakeDemo, capsys: pytest.CaptureFixture[str]
) -> None:
    lab.answer = "vampi"

    code = run_app(build_app(), ["demo"])

    captured = capsys.readouterr()
    assert code == ExitCode.OK
    assert "Demonstração cancelada" in captured.out
    assert "VAmPI local" in captured.err
    assert "Nada sai da máquina" in captured.err
    assert "Digite 'demo'" in lab.prompts[0]
    assert lab.cli.environment == {}
    assert not lab.root.exists()


def test_demo_usa_espaco_proprio_quando_ha_configuracao_de_outro_produto(
    lab: FakeDemo, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    other_products = tmp_path / "user-products"
    other_products.mkdir()
    marker = other_products / "target.yml"
    marker.write_text("perfil da pessoa", encoding="utf-8")
    monkeypatch.setenv("HDAST_PRODUCTS_DIR", str(other_products))
    monkeypatch.setenv("HDAST_ZAP_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("DOCKER_HOST", "tcp://example.invalid:2375")

    code = run_app(build_app(), ["demo"])

    env = lab.cli.environment
    assert code == ExitCode.OK
    assert lab.cli.approval_present_at_start
    assert Path(env["HDAST_PRODUCTS_DIR"]) == lab.root / "products"
    assert Path(env["HDAST_STATE_DIR"]) == lab.root / "state"
    assert Path(env["HDAST_RUNS_DIR"]) == lab.root / "runs"
    assert StackProjectSuffix(value=env["HDAST_STACK_PROJECT_SUFFIX"]).value
    assert env["DOCKER_HOST"].startswith(("unix://", "npipe://"))
    assert env["COMPOSE_DISABLE_ENV_FILE"] == "1"
    assert env["HDAST_LAB_PULL_POLICY"] == "never"
    assert "HDAST_ZAP_BASE_URL" not in env
    assert marker.read_text(encoding="utf-8") == "perfil da pessoa"
    assert (lab.root / "products" / "vampi" / "openapi3.yml").is_file()


@pytest.mark.parametrize(("flags", "running"), [([], False), (["--keep"], True)])
def test_demo_preserva_relatorio_e_respeita_keep_quando_ha_achados(
    lab: FakeDemo, capsys: pytest.CaptureFixture[str], flags: list[str], running: bool
) -> None:
    lab.cli.findings = True

    code = run_app(build_app(), ["demo", *flags])

    report = lab.root / "runs" / RUN_ID / "report.html"
    assert code == ExitCode.FINDINGS
    assert lab.cli.stack_running is running
    assert report.is_file()
    assert str(report) in capsys.readouterr().err
    assert lab.browser_offered


@pytest.mark.parametrize("failure", ["up_fails", "run_fails", "interrupt"])
def test_demo_desmonta_quando_ha_falha_ou_interrupcao(lab: FakeDemo, failure: str) -> None:
    setattr(lab.cli, failure, True)
    expected = ExitCode.INTERRUPTED if failure == "interrupt" else ExitCode.EXTERNAL_TOOL

    code = run_app(build_app(), ["demo"])

    assert code == expected
    assert not lab.cli.stack_running


def test_demo_preserva_relatorio_quando_a_desmontagem_falha(
    lab: FakeDemo, capsys: pytest.CaptureFixture[str]
) -> None:
    lab.cli.down_fails = True

    code = run_app(build_app(), ["demo"])

    captured = capsys.readouterr()
    assert code == ExitCode.EXTERNAL_TOOL
    assert str(lab.root / "state") in captured.err
    assert str(lab.root / "runs" / RUN_ID / "report.html") in captured.err


def test_demo_aparece_entre_os_comandos_para_comecar(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_app(build_app(), ["--help"])

    panel = capsys.readouterr().out.split("Comece por aqui", 1)[1].split("Cadastro e escopo", 1)[0]
    assert code == ExitCode.OK
    assert "demo" in panel
