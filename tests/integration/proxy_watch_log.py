"""Categorias da trava da vigia do proxy, lidas dos logs antes de derrubar a pilha (ADR 0093).

O proxy escreve a causa da primeira trava (`gate_watch_latch`) na própria saída, que some com o
contêiner no `stack down`. Este módulo lê essa saída e guarda só as categorias conhecidas de
`WatchCause`: nenhum texto bruto, caminho ou valor do log sai daqui. Falha de leitura vira um
estado sanitizado e nunca derruba o teste.
"""

import json
import re
import shutil
import subprocess
from collections.abc import Mapping
from typing import Any

from harness_dast.adapters.scope_proxy.watch_diagnostic import WatchCause

PROXY_SERVICE = "scope-proxy"
_DOCKER_TIMEOUT = 15
_KNOWN = frozenset(cause.value for cause in WatchCause)


def extract_categories(logs: str) -> list[str]:
    """Mantém apenas categorias reconhecidas de eventos JSON da vigia."""
    result: list[str] = []
    for line in logs.splitlines():
        try:
            record = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(record, dict) or record.get("event") != "gate_watch_latch":
            continue
        value = record.get("category")
        if isinstance(value, str) and value in _KNOWN:
            result.append(value)
    return result


def read_latch_categories(env: Mapping[str, str], project: str) -> dict[str, Any]:
    """Lê as categorias da trava no proxy do projeto Compose `project`.

    Returns:
        `{"status": ..., "categories": [...]}`. `status` é `ok`, `docker_unavailable`,
        `proxy_not_found` (nenhum ou mais de um contêiner do proxy) ou `collection_failed`.
    """
    docker = shutil.which("docker")
    if docker is None:
        return {"status": "docker_unavailable", "categories": []}
    try:
        found = _docker(
            docker,
            env,
            "ps",
            "-aq",
            "--no-trunc",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            f"label=com.docker.compose.service={PROXY_SERVICE}",
        ).split()
        if len(found) != 1 or not re.fullmatch(r"[0-9a-f]{64}", found[0]):
            return {"status": "proxy_not_found", "categories": []}
        logs = _docker(docker, env, "logs", found[0])
        return {"status": "ok", "categories": extract_categories(logs)}
    except (OSError, subprocess.SubprocessError):
        return {"status": "collection_failed", "categories": []}


def _docker(docker: str, env: Mapping[str, str], *args: str) -> str:
    done = subprocess.run(  # noqa: S603 - executável resolvido e argumentos fixos ou conferidos
        [docker, *args],
        env=dict(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_DOCKER_TIMEOUT,
        check=True,
    )
    return done.stdout + "\n" + done.stderr
