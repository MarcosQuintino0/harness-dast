"""Diagnostico sanitizado da vigia para a prova de laboratorio."""

import json
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from typing import Any

from harness_dast.adapters.scope_proxy.watch_diagnostic import WatchCause
from harness_dast.domain.errors import HarnessError
from tests.integration.lab_support import REPO
from tests.integration.v112_resource_support import ResourceGuard


def extract_categories(logs: str) -> list[str]:
    """Mantem apenas categorias reconhecidas de eventos JSON da vigia."""
    result: list[str] = []
    for line in logs.splitlines():
        try:
            record = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(record, dict) or record.get("event") != "gate_watch_latch":
            continue
        value = record.get("category")
        if isinstance(value, str) and value in {cause.value for cause in WatchCause}:
            result.append(value)
    return result


def collect_watch(
    guard: ResourceGuard,
    run: Callable[[tuple[str, ...]], str],
    logs: Callable[[str], str],
) -> dict[str, Any]:
    """Consulta contêiner próprio; falhas retornam somente estado sanitizado."""
    try:
        guard.before_down()
        found = run(
            (
                "ps",
                "-aq",
                "--no-trunc",
                "--filter",
                "label=com.docker.compose.project=hdast-codex",
                "--filter",
                "label=com.docker.compose.service=scope-proxy",
            )
        ).splitlines()
        if (
            len(found) != 1
            or not re.fullmatch(r"[0-9a-f]{64}", found[0])
            or guard.created is None
            or found[0] not in guard.created.containers
        ):
            return {"status": "ownership_unverified", "categories": []}
        return {"status": "ok", "categories": extract_categories(logs(found[0]))}
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        TypeError,
        AssertionError,
        HarnessError,
    ):
        return {"status": "collection_failed", "categories": []}


def docker_logs(env: Mapping[str, str]) -> Callable[[str], str]:
    """Lê logs com prazo, sem registrar texto ou diagnóstico bruto."""

    def read(container: str) -> str:
        executable = shutil.which("docker")
        if executable is None:
            raise OSError("Docker indisponível")
        result = subprocess.run(  # noqa: S603 - ID conferido e argumentos fixos
            [executable, "logs", container],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=True,
        )
        return result.stdout + "\n" + result.stderr

    return read
