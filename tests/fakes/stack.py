"""Falsos em memória das portas da pilha gerenciada, com comportamento."""

from datetime import datetime
from pathlib import Path

from harness_dast import __version__
from harness_dast.application.stack_models import (
    ComposeProject,
    OneShotResult,
    ServiceStatus,
    StackDirectories,
    StackState,
)
from harness_dast.domain.errors import ConfigError, ExternalToolError
from harness_dast.domain.nuclei_scope import NucleiScope
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run import RunId
from harness_dast.domain.stack_binding import StackDigests
from tests.fakes.host import FakeHost


class FakeCompose:
    """Registra o que foi subido; `fail_on` faz a chamada indicada falhar."""

    def __init__(self, host: FakeHost) -> None:
        self._host = host
        self.running: dict[str, ComposeProject] = {}
        self.envs: dict[str, dict[str, str]] = {}
        self.builds: dict[str, bool | None] = {}
        self.built_proxy_version = __version__
        self.calls: list[tuple[str, str]] = []
        self.fail_on: str | None = None

    def build(
        self, project: ComposeProject, env: dict[str, str], services: tuple[str, ...]
    ) -> None:
        self.calls.append(("build", project.name))
        if self.fail_on == "build":
            raise ExternalToolError("build falhou")
        images = self._host.compose_images(services, env)
        self._host.present.update(images.values())
        self._host.versions[images["scope-proxy"]] = self.built_proxy_version

    def up(
        self,
        project: ComposeProject,
        env: dict[str, str],
        *,
        build: bool | None,
        timeout_seconds: int,
    ) -> None:
        self.calls.append(("up", project.name))
        self.builds[project.name] = build
        if self.fail_on == "up":
            raise ExternalToolError("docker falhou", hint="tente de novo")
        self.running[project.name] = project
        self.envs[project.name] = dict(env)

    def down(self, project: ComposeProject, env: dict[str, str], *, timeout_seconds: int) -> None:
        self.calls.append(("down", project.name))
        if self.fail_on == "down":
            raise ExternalToolError("docker falhou", hint="tente de novo")
        self.running.pop(project.name, None)

    def run_once(
        self,
        project: ComposeProject,
        env: dict[str, str],
        service: str,
        args: tuple[str, ...],
        *,
        container_name: str,
        timeout_seconds: int,
        mounts: tuple[str, ...] = (),
    ) -> OneShotResult:
        self.calls.append(("run_once", project.name))
        return OneShotResult(exit_code=0, stdout="")

    def kill_container(
        self, project: ComposeProject, env: dict[str, str], container_name: str
    ) -> None:
        self.calls.append(("kill_container", container_name))

    def status(self, project: ComposeProject, env: dict[str, str]) -> tuple[ServiceStatus, ...]:
        if project.name not in self.running:
            return ()
        return tuple(
            ServiceStatus(project=project.name, service=name, state="running", health="healthy")
            for name in project.services or ("pilot",)
        )


class InMemoryStackState:
    """Estado da pilha em memória, com as pastas em um diretório temporário."""

    def __init__(self, base: Path) -> None:
        self._base = base
        self.state: StackState | None = None

    def load(self) -> StackState | None:
        return self.state

    def save(self, state: StackState) -> None:
        self.state = state

    def clear(self) -> None:
        self.state = None

    def directories_for(self, run_id: str) -> StackDirectories:
        folders = {
            name: self._base / run_id / name
            for name in ("policy", "audit", "policy-nuclei", "audit-nuclei")
        }
        for folder in folders.values():
            folder.mkdir(parents=True)
        return StackDirectories(
            policy_dir=folders["policy"],
            audit_dir=folders["audit"],
            nuclei_policy_dir=folders["policy-nuclei"],
            nuclei_audit_dir=folders["audit-nuclei"],
        )

    def location(self) -> Path:
        return self._base / "stack.json"


class RecordingPolicyStore:
    """Registra a política publicada e cria o KILL de verdade na pasta dada."""

    def __init__(self) -> None:
        self.published: list[tuple[str, datetime, Path]] = []
        self.published_nuclei: list[tuple[str, datetime, Path, NucleiScope | None]] = []

    def publish(
        self, profile: ProductProfile, run_id: RunId, not_after: datetime, directory: Path
    ) -> Path:
        self.published.append((run_id.value, not_after, directory))
        path = directory / "policy.json"
        path.write_text("{}", encoding="utf-8")
        return path

    def publish_nuclei(
        self,
        profile: ProductProfile,
        run_id: RunId,
        not_after: datetime,
        directory: Path,
        nuclei: NucleiScope | None,
    ) -> Path:
        self.published_nuclei.append((run_id.value, not_after, directory, nuclei))
        path = directory / "policy.json"
        path.write_text("{}", encoding="utf-8")
        return path

    def trigger_kill(self, directory: Path) -> bool:
        if not directory.is_dir():
            raise ConfigError("sem pasta")
        existed = (directory / "KILL").exists()
        (directory / "KILL").touch()
        return not existed

    def kill_active(self, directory: Path) -> bool:
        return (directory / "KILL").exists()


class CountingRandom:
    """Devolve valores diferentes e previsíveis a cada chamada."""

    def __init__(self) -> None:
        self._count = 0

    def token_hex(self, nbytes: int) -> str:
        self._count += 1
        return f"{self._count:0{2 * nbytes}x}"


class FakeStopper:
    """Para varreduras de mentira; `reachable=False` simula o ZAP fora do ar."""

    def __init__(self, *, reachable: bool = True, running: int = 2) -> None:
        self._reachable = reachable
        self._running = running
        self.calls = 0

    def stop_all_scans(self) -> int:
        self.calls += 1
        if not self._reachable:
            raise ExternalToolError("O ZAP não respondeu.", hint="suba o ZAP")
        return self._running


class FakeBindingSource:
    """Vínculo gravado e hashes de agora definidos pelo teste (implementa `StackBindingSource`)."""

    def __init__(
        self, recorded: StackDigests | None, current: StackDigests, *, unreadable: bool = False
    ) -> None:
        self.recorded_value = recorded
        self.current_value = current
        self.unreadable = unreadable

    def recorded(self, policy_dir: Path) -> StackDigests | None:
        if self.unreadable:
            raise ConfigError("política ilegível", hint="recrie a pilha")
        return self.recorded_value

    def current(self, product: str) -> StackDigests:
        return self.current_value
