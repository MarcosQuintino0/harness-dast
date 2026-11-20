"""Motor do Nuclei pelo `docker compose run --rm` de uso único (implementa `NucleiEngine`).

O que garante:
- Roda pelo `ComposeRunner.run_once` do P6: sem shell (argumentos como lista), entrada padrão
  fechada, prazo, e contêiner morto antes de o erro de prazo subir.
- A lista de modelos e o arquivo de segredos entram por montagem SOMENTE LEITURA. O token nunca
  vai para argumento, variável de ambiente nem log: o ambiente passado ao runner é o da pilha e
  nada mais, e a saída de erro do contêiner nem é devolvida.
- Enquanto o contêiner roda, `stop_requested` é consultado a cada `poll_seconds`; se disser
  `True`, o contêiner é derrubado pelo nome (`kill_container`) e a saída parcial é devolvida.
- A saída bruta (stdout em JSONL) é gravada num diretório temporário privado (`0700`, arquivo
  `0600`); `discard` o apaga.
O que não faz: não decide o que rodar, não lê a saída e não conhece o token.
"""

import os
import shutil
import tempfile
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

from harness_dast.application.nuclei_ports import (
    CATALOG_ROOT,
    SECRETS_MOUNT,
    TEMPLATES_MOUNT,
    NucleiRunResult,
    NucleiRunSpec,
)
from harness_dast.application.stack_models import ComposeProject, OneShotResult
from harness_dast.application.stack_ports import ComposeRunner
from harness_dast.domain.errors import ExternalToolError, HarnessError

__all__ = ["POLL_SECONDS", "DockerNucleiEngine"]

POLL_SECONDS: Final = 1.0
"""Intervalo com que o motor pergunta se deve parar (`KILL`, janela, prazo)."""
SERVICE: Final = "nuclei"
_RAW_PREFIX = "hdast-nuclei-raw-"
_RAW_NAME = "nuclei.jsonl"


class _Job(threading.Thread):
    """Roda o contêiner numa linha própria, para o chamador poder vigiar a parada."""

    def __init__(self, work: Callable[[], OneShotResult]) -> None:
        super().__init__(daemon=True)
        self._work = work
        self.result: OneShotResult | None = None
        self.error: HarnessError | None = None

    def run(self) -> None:
        try:
            self.result = self._work()
        except HarnessError as error:
            self.error = error


class DockerNucleiEngine:
    """Implementa `NucleiEngine` sobre o `ComposeRunner` (veja o docstring do módulo)."""

    def __init__(
        self,
        compose: ComposeRunner,
        project: ComposeProject,
        env: Mapping[str, str],
        *,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        """Cria o motor.

        Args:
            compose: Docker Compose (a chamada `run_once` e `kill_container`).
            project: Projeto da pilha (o do `StackState`).
            env: Ambiente que o compose precisa para interpolar o arquivo da pilha (as pastas de
                política e a chave do ZAP). Nunca recebe segredo de login.
            poll_seconds: Intervalo da consulta de parada.
        """
        self._compose = compose
        self._project = project
        self._env = dict(env)
        self._poll = poll_seconds

    def run(self, spec: NucleiRunSpec, stop_requested: Callable[[], bool]) -> NucleiRunResult:
        """Roda o Nuclei uma vez; veja `NucleiEngine.run`."""
        raw_dir = Path(tempfile.mkdtemp(prefix=_RAW_PREFIX))
        list_dir = raw_dir.with_name(raw_dir.name + "-list")
        try:
            list_dir.mkdir(mode=0o700)
            mounts = (self._templates_mount(list_dir, spec), *_secrets_mount(spec))
            job = _Job(lambda: self._once(spec, mounts))
            killed = self._watch(job, spec, stop_requested)
            result = _outcome(job)
            raw = raw_dir / _RAW_NAME
            _write_private(raw, result.stdout)
            return NucleiRunResult(exit_code=result.exit_code, raw_jsonl=raw, killed=killed)
        except BaseException:
            shutil.rmtree(raw_dir, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(list_dir, ignore_errors=True)

    def discard(self, raw_jsonl: Path) -> None:
        """Apaga a saída bruta e o diretório privado dela; só toca no que este motor criou."""
        directory = raw_jsonl.parent
        if directory.name.startswith(_RAW_PREFIX) and raw_jsonl.name == _RAW_NAME:
            shutil.rmtree(directory, ignore_errors=True)

    def _once(self, spec: NucleiRunSpec, mounts: tuple[str, ...]) -> OneShotResult:
        return self._compose.run_once(
            self._project,
            dict(self._env),
            SERVICE,
            spec.args,
            container_name=spec.container_name,
            timeout_seconds=spec.timeout_seconds,
            mounts=mounts,
        )

    def _watch(self, job: _Job, spec: NucleiRunSpec, stop_requested: Callable[[], bool]) -> bool:
        """Espera o contêiner e o derruba se `stop_requested` disser `True`; devolve se derrubou."""
        killed = False
        job.start()
        try:
            while True:
                job.join(self._poll)
                if not job.is_alive():
                    return killed
                if not killed and stop_requested():
                    killed = True
                    self._compose.kill_container(
                        self._project, dict(self._env), spec.container_name
                    )
        except KeyboardInterrupt:
            self._compose.kill_container(self._project, dict(self._env), spec.container_name)
            raise

    @staticmethod
    def _templates_mount(directory: Path, spec: NucleiRunSpec) -> str:
        path = directory / "templates.txt"
        lines = "".join(f"{CATALOG_ROOT}/{template}\n" for template in spec.templates)
        _write_private(path, lines, mode=0o644)
        return f"{path}:{TEMPLATES_MOUNT}:ro"


def _outcome(job: _Job) -> OneShotResult:
    if job.error is not None:
        raise job.error
    if job.result is None:
        raise ExternalToolError(
            "O contêiner do Nuclei terminou sem resultado.",
            hint="Rode de novo; se repetir, confira o Docker Desktop.",
        )
    return job.result


def _secrets_mount(spec: NucleiRunSpec) -> tuple[str, ...]:
    if spec.secrets_path is None:
        return ()
    return (f"{spec.secrets_path}:{SECRETS_MOUNT}:ro",)


def _write_private(path: Path, text: str, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
