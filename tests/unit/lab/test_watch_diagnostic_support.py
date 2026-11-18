"""Diagnóstico da vigia em logs locais, sem Docker nem conteúdo bruto nas métricas."""

import json
import subprocess
from collections.abc import Callable

import pytest

from tests.integration.lab_resource_support import Inventory, ResourceGuard
from tests.integration.proxy_watch_log import extract_categories
from tests.integration.watch_diagnostic_support import collect_watch

CONTAINER = "a" * 64


def _guard() -> ResourceGuard:
    state = Inventory(frozenset({CONTAINER}), frozenset(), frozenset())
    guard = ResourceGuard(lambda: state)
    guard.created = state
    return guard


def _run(ids: str) -> Callable[[tuple[str, ...]], str]:
    return lambda _: ids


def test_extrai_somente_categoria_permitida_e_ignora_conteudo() -> None:
    raw = "\n".join(
        (
            "senha-confidencial",
            "{erro",
            '{"event":"gate_watch_latch","category":"hash","secret":"senha-confidencial"}',
            '{"event":"gate_watch_latch","category":"senha-confidencial"}',
            '{"event":"outro","category":"access"}',
        )
    )
    assert extract_categories(raw) == ["hash"]
    result = collect_watch(_guard(), _run(CONTAINER), lambda _: raw)
    assert result == {"status": "ok", "categories": ["hash"]}
    assert "senha-confidencial" not in json.dumps(result)


@pytest.mark.parametrize("ids", ["", "b" * 64, "a" * 63, CONTAINER + "\n" + CONTAINER])
def test_recusa_contêiner_invalido_ambiguo_ou_alheio(ids: str) -> None:
    def forbidden(_: str) -> str:
        raise AssertionError("não deve consultar logs")

    assert collect_watch(_guard(), _run(ids), forbidden) == {
        "status": "ownership_unverified",
        "categories": [],
    }


def test_falha_de_consulta_retorna_estado_sem_erro_bruto() -> None:
    def fail(_: str) -> str:
        raise OSError("senha-confidencial")

    result = collect_watch(_guard(), _run(CONTAINER), fail)
    assert result == {"status": "collection_failed", "categories": []}
    assert "senha-confidencial" not in json.dumps(result)


def test_recusa_se_inventario_mudou_antes_da_coleta() -> None:
    guard = _guard()
    guard.inspect = lambda: Inventory(frozenset(), frozenset(), frozenset())
    result = collect_watch(guard, _run(CONTAINER), lambda _: "")
    assert result == {"status": "collection_failed", "categories": []}


def test_timeout_de_logs_nao_expoe_saida_parcial() -> None:
    def fail(_: str) -> str:
        raise subprocess.TimeoutExpired("docker", 15, output="senha-confidencial")

    result = collect_watch(_guard(), _run(CONTAINER), fail)
    assert result == {"status": "collection_failed", "categories": []}
    assert "senha-confidencial" not in json.dumps(result)


def test_captura_inventario_estavel_quando_solicitado() -> None:
    state = Inventory(frozenset({CONTAINER}), frozenset(), frozenset())
    guard = ResourceGuard(lambda: state)
    result = collect_watch(
        guard,
        _run(CONTAINER),
        lambda _: '{"event":"gate_watch_latch","category":"identity"}',
        capture_created=True,
    )
    assert result == {"status": "ok", "categories": ["identity"]}
    assert guard.created == state


def test_recusa_captura_quando_inventario_incompleto() -> None:
    guard = ResourceGuard(lambda: Inventory(frozenset(), frozenset(), frozenset()))
    result = collect_watch(guard, _run(CONTAINER), lambda _: "", capture_created=True)
    assert result == {"status": "collection_failed", "categories": []}
    assert guard.created is None
