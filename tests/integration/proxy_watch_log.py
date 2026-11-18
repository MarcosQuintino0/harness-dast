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
from collections.abc import Callable, Mapping
from functools import partial
from typing import Literal, TypedDict

from harness_dast.adapters.scope_proxy.watch_diagnostic import WatchCause

PROXY_SERVICE = "scope-proxy"
_DOCKER_TIMEOUT = 15
_KNOWN = frozenset(cause.value for cause in WatchCause)
Runner = Callable[[tuple[str, ...]], str]


class WatchResult(TypedDict):
    """Resultado da coleta, restrito ao estado e às categorias sanitizadas."""

    status: Literal["ok", "docker_unavailable", "proxy_not_found", "collection_failed"]
    categories: list[str]


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


def read_latch_categories(run: Runner | None, project: str) -> WatchResult:
    """Lê as categorias da trava no proxy do projeto Compose `project`.

    Returns:
        `{"status": ..., "categories": [...]}`. `status` é `ok`, `docker_unavailable`,
        `proxy_not_found` (nenhum ou mais de um contêiner do proxy) ou `collection_failed`.
    """
    if run is None:
        return {"status": "docker_unavailable", "categories": []}
    try:
        found = run(
            (
                "ps",
                "-aq",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={project}",
                "--filter",
                f"label=com.docker.compose.service={PROXY_SERVICE}",
            )
        ).split()
        if len(found) != 1 or not re.fullmatch(r"[0-9a-f]{64}", found[0]):
            return {"status": "proxy_not_found", "categories": []}
        logs = run(("logs", found[0]))
        return {"status": "ok", "categories": extract_categories(logs)}
    except (OSError, subprocess.SubprocessError):
        return {"status": "collection_failed", "categories": []}


def docker_runner(env: Mapping[str, str]) -> Runner | None:
    """Monta o executor real com prazo por comando, se o Docker estiver instalado."""
    docker = shutil.which("docker")
    return None if docker is None else partial(_docker, docker, env)


def read_docker_latch_categories(env: Mapping[str, str], project: str) -> WatchResult:
    """Coleta categorias da vigia com o executor real do Docker."""
    return read_latch_categories(docker_runner(env), project)


def _docker(docker: str, env: Mapping[str, str], args: tuple[str, ...]) -> str:
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
