"""Montagem do laboratório isolado da demonstração e adaptação das saídas da CLI."""

import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from harness_dast import __version__
from harness_dast.adapters.docker.compose import default_repo_root, run_subprocess
from harness_dast.adapters.docker.host import SystemHost
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.application.doctor_report import DoctorReport
from harness_dast.application.doctor_stack import DoctorStackChecks
from harness_dast.application.lab_targets import VAMPI
from harness_dast.application.stack_images import StackImages
from harness_dast.cli.output import SCHEMA_VERSION, Envelope, build_failure
from harness_dast.domain.errors import ConfigError, ExitCode, ExternalToolError
from harness_dast.domain.run import is_run_id

DEMO_MINUTES = 5
DOCKER_GUIDE = "docs/comecar/docker.md#preparar-as-imagens-da-demo"
_CHILD_TIMEOUT_SECONDS = 600
_PROFILE_FILES = ("target.yml", "data-rules.yml", "flows.yml")
_OS_ENV = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "TEMP",
    "TMP",
    "TMPDIR",
)


def _docker_host(platform: str, home: Path) -> str:
    if platform == "win32":
        return "npipe:////./pipe/docker_engine"
    desktop_socket = home / ".docker/run/docker.sock"
    if platform == "darwin" and desktop_socket.is_socket():
        return f"unix://{desktop_socket}"
    return "unix:///var/run/docker.sock"


def demo_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """Mantém só variáveis do sistema necessárias e fixa o motor Docker local."""
    return {
        **{name: environ[name] for name in _OS_ENV if name in environ},
        "DOCKER_HOST": _docker_host(sys.platform, Path.home()),
        "COMPOSE_DISABLE_ENV_FILE": "1",
        "HDAST_LAB_PULL_POLICY": "never",
    }


def check_demo_environment(environ: Mapping[str, str]) -> DoctorReport:
    """Reutiliza o diagnóstico da pilha e exige todas as imagens locais e portas livres."""
    host = SystemHost(environ)
    checks = DoctorStackChecks(host, StackImages(host, __version__), environ)
    return DoctorReport.from_checks(checks.execute(VAMPI, offline=True))


@dataclass(frozen=True)
class DemoStep:
    """Envelope e código de saída de uma etapa executada pela CLI existente."""

    code: ExitCode
    envelope: Envelope


class DemoSession:
    """Estado, perfil e execuções exclusivos de uma demonstração."""

    def __init__(
        self, directory: Path, repo: Path, environ: Mapping[str, str], project_suffix: str
    ) -> None:
        """Fixa a raiz temporária e o ambiente que os subprocessos receberão."""
        self.directory = directory
        self.repo = repo
        self.products = directory / "products"
        self.state = directory / "state"
        self.runs = directory / "runs"
        self.environ = {
            **environ,
            "HDAST_PRODUCTS_DIR": str(self.products),
            "HDAST_STATE_DIR": str(self.state),
            "HDAST_RUNS_DIR": str(self.runs),
            "HDAST_STACK_PROJECT_SUFFIX": project_suffix,
            # Contas públicas semeadas pelo VAmPI ao preparar a base do laboratório.
            "VAMPI_USER_A_USERNAME": "name1",
            "VAMPI_USER_A_PASSWORD": "pass1",
            "VAMPI_USER_B_USERNAME": "name2",
            "VAMPI_USER_B_PASSWORD": "pass2",
            "VAMPI_ADMIN_USERNAME": "admin",
            "VAMPI_ADMIN_PASSWORD": "pass1",
        }

    def install_profile(self) -> None:
        """Copia o perfil distribuído com o lab e confere que ele só autoriza o VAmPI local."""
        source = self.repo / "lab" / VAMPI.name
        product = self.products / VAMPI.name
        try:
            product.mkdir(parents=True)
            for filename in _PROFILE_FILES:
                shutil.copyfile(source / "product-profile" / filename, product / filename)
            shutil.copyfile(source / "openapi3.yml", product / "openapi3.yml")
        except OSError:
            raise ConfigError(
                "Não consegui copiar o perfil do VAmPI para a pasta temporária.",
                hint="Confira o checkout do laboratório e a permissão da pasta temporária.",
            ) from None
        profile = FileProfileRepository(self.products).load(VAMPI.name)
        endpoint = ("http", VAMPI.host, 5000)
        if (
            profile.environment.base_url != f"http://{VAMPI.host}:5000"
            or profile.scan.oast
            or any((rule.scheme, rule.host, rule.port) != endpoint for rule in profile.scope.allow)
        ):
            raise ConfigError(
                "O perfil embutido da demo precisa autorizar somente o VAmPI local.",
                hint="Restaure lab/vampi/product-profile/target.yml no checkout.",
            )

    def start(self) -> DemoStep:
        """Sobe a pilha existente com o VAmPI em modo vulnerável."""
        return self._invoke("stack", "up", VAMPI.name, "--vulnerable")

    def run(self) -> DemoStep:
        """Executa o fluxo padrão com um prazo de varredura reduzido."""
        return self._invoke("run", VAMPI.name, "--max-minutes", str(DEMO_MINUTES))

    def stop(self) -> DemoStep:
        """Derruba apenas a pilha registrada no estado da sessão."""
        return self._invoke("stack", "down")

    def report_path(self, run: DemoStep) -> Path | None:
        """Devolve a página local se o run chegou a gravá-la."""
        run_id = run.envelope.run_id
        if run_id is None or not is_run_id(run_id):
            return None
        path = self.runs / run_id / "report.html"
        return path if path.is_file() else None

    def _invoke(self, *args: str) -> DemoStep:
        try:
            result = run_subprocess(
                [sys.executable, "-I", "-m", "harness_dast", "--json", *args],
                self.environ,
                self.repo,
                _CHILD_TIMEOUT_SECONDS,
            )
            code = ExitCode(result.returncode)
            envelope = Envelope.model_validate_json(result.stdout)
            if envelope.schema_version == SCHEMA_VERSION and envelope.ok == (code in (0, 1)):
                return DemoStep(code, envelope)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            # A saída bruta dos processos pode conter detalhes internos da pilha.
            pass
        error = ExternalToolError(
            f"A etapa 'hdast {' '.join(args)}' da demo não retornou um resultado válido.",
            hint=f"Confira a instalação da CLI e consulte {DOCKER_GUIDE}.",
        )
        return DemoStep(error.exit_code, build_failure(error))


def open_demo_session(environ: Mapping[str, str]) -> DemoSession:
    """Localiza os arquivos do checkout e reserva uma pasta temporária privada."""
    repo = default_repo_root()
    try:
        directory = Path(tempfile.mkdtemp(prefix="demo"))
    except OSError:
        raise ConfigError(
            "Não consegui criar a pasta temporária da demo.",
            hint="Confira se há espaço em disco e permissão para gravar na pasta temporária.",
        ) from None
    return DemoSession(directory, repo, environ, f"-demo{uuid4().hex[:12]}")
