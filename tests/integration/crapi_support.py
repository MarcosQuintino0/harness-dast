"""Diagnóstico sanitizado e consultas locais de controle da prova do crAPI."""

import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any

from harness_dast.application.lab_targets import CRAPI_PROJECT
from harness_dast.application.stack import MAIN_PROJECT
from tests.integration.lab_support import REPO, CliResult, LabCli, stack_suffix


def project() -> str:
    """Devolve o nome atual do projeto Compose principal."""
    return MAIN_PROJECT + stack_suffix()


def crapi_project() -> str:
    """Devolve o nome atual do projeto Compose do crAPI."""
    return CRAPI_PROJECT + stack_suffix()


def run_cli(cli: LabCli, *args: str, timeout: int = 420) -> tuple[CliResult, dict[str, Any]]:
    """Executa CLI sem repetir a preparação da aprovação e mede o tempo."""
    started = datetime.now(UTC).isoformat()
    tick = time.monotonic()
    done = subprocess.run(  # noqa: S603 - módulo e comandos de teste fixos
        [sys.executable, "-m", "harness_dast", "--json", *args],
        env=cli.env,
        cwd=REPO,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    try:
        parsed = json.loads(done.stdout)
    except ValueError:
        parsed = {}
    envelope = parsed if isinstance(parsed, dict) else {}
    result = CliResult(done.returncode, envelope, done.stdout, done.stderr)
    error = envelope.get("error")
    metrics = {
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "duration_seconds": round(time.monotonic() - tick, 3),
        "exit_code": done.returncode,
        "run_id": envelope.get("run_id"),
        "error_code": error.get("code") if isinstance(error, dict) else None,
    }
    return result, metrics


def observe_status(cli: LabCli) -> dict[str, Any]:
    """Lê estado da pilha e da aprovação pela CLI, sem copiar saída arbitrária."""
    stack, stack_timing = run_cli(cli, "stack", "status")
    approval, approval_timing = run_cli(cli, "profile", "approval", "crapi")
    return {
        "stack_timing": stack_timing,
        "approval_timing": approval_timing,
        "stack_run_id": stack.data.get("run_id"),
        "binding": stack.data.get("binding"),
        "stale_parts": stack.data.get("stale_parts"),
        "approval_state": approval.data.get("state"),
        "approval_time": approval.data.get("approved_at"),
        "changed_blocks": approval.data.get("changed_blocks"),
    }


def _docker(*args: str) -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise AssertionError("Docker indisponível para as consultas de controle.")
    result = subprocess.run(  # noqa: S603 - somente consultas de controle com argumentos fixos
        [docker, *args], capture_output=True, text=True, encoding="utf-8", timeout=30, check=False
    )
    if result.returncode:
        raise AssertionError("Consulta de controle Docker falhou; confira o daemon e a pilha.")
    return result.stdout.strip()


def _containers(project: str) -> list[str]:
    return _docker(
        "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"
    ).splitlines()


def _inspect(container: str, template: str) -> Any:
    return json.loads(_docker("inspect", "--format", template, container))


def inspect_topology() -> set[str]:
    """Confere redes e portas, devolvendo nomes dos volumes anônimos ou nomeados usados."""
    main_project = project()
    target_project = crapi_project()
    for network in (f"{main_project}_lab_net", f"{target_project}_crapi_net"):
        assert _docker("network", "inspect", "--format", "{{json .Internal}}", network) == "true"
    main = _containers(main_project)
    target = _containers(target_project)
    assert main
    assert target
    volumes: set[str] = set()
    zap_found = False
    workshop_found = False
    target_networks = {
        name
        for container in target
        for name in _inspect(container, "{{json .NetworkSettings.Networks}}")
    }
    for container in main + target:
        service = _inspect(
            container, '{{json (index .Config.Labels "com.docker.compose.service")}}'
        )
        networks = _inspect(container, "{{json .NetworkSettings.Networks}}")
        ports = _inspect(container, "{{json .NetworkSettings.Ports}}") or {}
        if service == "zap":
            zap_found = True
            assert not set(networks) & target_networks
        if service == "crapi-workshop":
            workshop_found = True
            assert set(networks) == {f"{target_project}_crapi_net"}
        for bindings in ports.values():
            for binding in bindings or []:
                assert binding["HostIp"] in {"127.0.0.1", "::1"}
        if container in target:
            names = _docker(
                "inspect",
                "--format",
                '{{range .Mounts}}{{if eq .Type "volume"}}{{println .Name}}{{end}}{{end}}',
                container,
            )
            volumes.update(names.splitlines())
    assert zap_found
    assert workshop_found
    assert volumes
    return volumes


def assert_volumes_removed(volumes: set[str]) -> None:
    """Verifica por listagem se os volumes observados na pilha desapareceram."""
    remaining = set(_docker("volume", "ls", "-q").splitlines())
    assert not volumes & remaining
