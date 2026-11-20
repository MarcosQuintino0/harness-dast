"""Leitura sanitizada das categorias da vigia sem executar Docker."""

import subprocess
from collections.abc import Mapping

import pytest

from tests.integration.proxy_watch_log import read_latch_categories

PROJECT = "hdast-teste"
CONTAINER_ID = "a" * 64
LIST_PROXY = (
    "ps",
    "-aq",
    "--no-trunc",
    "--filter",
    f"label=com.docker.compose.project={PROJECT}",
    "--filter",
    "label=com.docker.compose.service=scope-proxy",
)
READ_LOGS = ("logs", CONTAINER_ID)


class FakeDocker:
    """Devolve a saída configurada por comando e recusa comandos inesperados."""

    def __init__(self, outcomes: Mapping[tuple[str, ...], str | Exception]) -> None:
        self.outcomes = outcomes

    def __call__(self, args: tuple[str, ...]) -> str:
        outcome = self.outcomes[args]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_reports_docker_unavailable_quando_executor_ausente() -> None:
    result = read_latch_categories(None, PROJECT)

    assert result == {"status": "docker_unavailable", "categories": []}


@pytest.mark.parametrize("containers", ["", f"{CONTAINER_ID}\n{'b' * 64}"], ids=["zero", "dois"])
def test_reports_proxy_not_found_quando_quantidade_de_containers_difere_de_um(
    containers: str,
) -> None:
    docker = FakeDocker({LIST_PROXY: containers})

    result = read_latch_categories(docker, PROJECT)

    assert result == {"status": "proxy_not_found", "categories": []}


@pytest.mark.parametrize("container_id", ["a" * 63, "z" * 64], ids=["tamanho", "hexadecimal"])
def test_reports_proxy_not_found_quando_id_invalido(container_id: str) -> None:
    docker = FakeDocker({LIST_PROXY: container_id})

    result = read_latch_categories(docker, PROJECT)

    assert result == {"status": "proxy_not_found", "categories": []}


def test_reports_collection_failed_quando_listagem_falha() -> None:
    failure = subprocess.CalledProcessError(1, LIST_PROXY, stderr="detalhe interno do motor")
    docker = FakeDocker({LIST_PROXY: failure})

    result = read_latch_categories(docker, PROJECT)

    assert result == {"status": "collection_failed", "categories": []}


def test_reports_collection_failed_quando_leitura_excede_prazo() -> None:
    failure = subprocess.TimeoutExpired(READ_LOGS, 15, output="saída parcial do contêiner")
    docker = FakeDocker({LIST_PROXY: CONTAINER_ID, READ_LOGS: failure})

    result = read_latch_categories(docker, PROJECT)

    assert result == {"status": "collection_failed", "categories": []}


def test_preserves_categories_quando_log_tem_eventos_validos() -> None:
    logs = (
        '{"event":"gate_watch_latch","category":"metadata","detail":"valor bruto"}\n'
        '{"event":"gate_watch_latch","category":"hash"}'
    )
    docker = FakeDocker({LIST_PROXY: CONTAINER_ID, READ_LOGS: logs})

    result = read_latch_categories(docker, PROJECT)

    assert result == {"status": "ok", "categories": ["metadata", "hash"]}


@pytest.mark.parametrize(
    "logs",
    [
        "{texto incompleto",
        "[]",
        '{"event":"gate_watch_latch"}',
        '{"event":"gate_watch_latch","category":["hash"]}',
        '{"event":"outro_evento","category":"hash"}',
        '{"event":"gate_watch_latch","category":"approval_changed"}',
    ],
    ids=["json", "objeto", "ausente", "tipo", "evento", "categoria"],
)
def test_ignores_lines_quando_log_tem_conteudo_invalido(logs: str) -> None:
    docker = FakeDocker({LIST_PROXY: CONTAINER_ID, READ_LOGS: logs})

    result = read_latch_categories(docker, PROJECT)

    assert result == {"status": "ok", "categories": []}
