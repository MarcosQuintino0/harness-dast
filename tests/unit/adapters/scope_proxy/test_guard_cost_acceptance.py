"""Regressões independentes da integridade das fontes usadas na concessão."""

import asyncio
import os
from pathlib import Path
from threading import Event, Thread

import pytest

import harness_dast.adapters.scope_proxy.approval_watch as watch_module
from harness_dast.adapters.scope_proxy.approval_watch import file_signature
from harness_dast.adapters.scope_proxy.decision import Reason
from harness_dast.adapters.scope_proxy.gate_watch import GateWatch
from harness_dast.adapters.scope_proxy.grant_queue import GrantQueue
from tests.unit.adapters.scope_proxy.test_authorization_acceptance import rig


@pytest.mark.parametrize("source", ["approval", "profile"])
def test_mutacao_sem_mudar_tamanho_ou_mtime_trava_concessoes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    # No Windows ctime não participa da assinatura; só o hash percebe esta mutação.
    monkeypatch.setattr(
        watch_module, "file_signature", lambda value: file_signature(value, windows=True)
    )
    engine, _, approval, profile = rig(tmp_path)
    path = approval if source == "approval" else profile
    original = path.read_bytes()
    before = path.stat()
    signature = file_signature(before, windows=True)
    changed = bytes([original[0] ^ 1]) + original[1:]
    path.write_bytes(changed)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert file_signature(path.stat(), windows=True) == signature

    async def scenario() -> None:
        queue = GrantQueue(engine, sleep=asyncio.sleep)
        watch = engine._gate._watch
        assert watch is not None
        watch.run_once()
        assert (await queue.acquire()).reason is Reason.APPROVAL_CHANGED
        path.write_bytes(original)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        watch.run_once()
        assert (await queue.acquire()).reason is Reason.APPROVAL_CHANGED

    try:
        asyncio.run(scenario())
    finally:
        engine.close()


def test_leitura_lenta_nao_renova_snapshot_ao_terminar() -> None:
    now = [0.0]
    calls = [0]

    def detect() -> Reason | None:
        calls[0] += 1
        if calls[0] == 2:
            now[0] = 0.201
        return None

    watch = GateWatch(detect, lambda: now[0])
    try:
        watch.run_once()
        assert watch.check() is Reason.APPROVAL_CHANGED
        now[0] = 0.202
        watch.run_once()
        assert watch.check() is Reason.APPROVAL_CHANGED
    finally:
        watch.close()


def test_limite_de_idade_aceita_200_ms_e_recusa_acima() -> None:
    now = [0.0]
    watch = GateWatch(lambda: None, lambda: now[0])
    try:
        now[0] = 0.2
        assert watch.check() is None
        now[0] = 0.201
        assert watch.check() is Reason.APPROVAL_CHANGED
    finally:
        watch.close()


def test_excecao_na_verificacao_fecha_ate_apos_leitura_bem_sucedida() -> None:
    broken = [False]

    def detect() -> Reason | None:
        if broken[0]:
            raise OSError("falha de leitura")
        return None

    watch = GateWatch(detect, lambda: 0.0)
    try:
        broken[0] = True
        with pytest.raises(OSError, match="falha de leitura"):
            watch.run_once()
        broken[0] = False
        watch.run_once()
        assert watch.check() is Reason.APPROVAL_CHANGED
    finally:
        watch.close()


def test_encerramento_durante_leitura_nao_reabre_apos_retorno() -> None:
    entered = Event()
    release = Event()
    calls = [0]

    def detect() -> Reason | None:
        calls[0] += 1
        if calls[0] > 1:
            entered.set()
            release.wait()
        return None

    watch = GateWatch(detect, lambda: 0.0)
    reader = Thread(target=watch.run_once, daemon=True)
    reader.start()
    try:
        assert entered.wait(2)
        watch.close()
        assert watch.check() is Reason.APPROVAL_CHANGED
    finally:
        release.set()
        reader.join(2)
    assert not reader.is_alive()
    assert watch.check() is Reason.APPROVAL_CHANGED


def test_fila_responde_com_leitura_da_vigia_bloqueada(tmp_path: Path) -> None:
    engine, clocks, _, _ = rig(tmp_path)
    watch = engine._gate._watch
    assert watch is not None
    entered = Event()
    release = Event()
    finished = Event()
    results: list[Reason] = []

    def blocked_read() -> Reason | None:
        entered.set()
        release.wait()
        return None

    def acquire() -> None:
        async def scenario() -> None:
            queue = GrantQueue(engine, sleep=asyncio.sleep)
            results.append((await queue.acquire()).reason)
            clocks.mono += 0.201
            results.append((await queue.acquire()).reason)

        try:
            asyncio.run(scenario())
        finally:
            finished.set()

    watch._detect = blocked_read
    reader = Thread(target=watch.run_once, daemon=True)
    requester = Thread(target=acquire, daemon=True)
    reader.start()
    try:
        assert entered.wait(2)
        requester.start()
        assert finished.wait(2), "fila bloqueada enquanto vigia aguarda leitura"
        assert results == [Reason.ALLOWED, Reason.APPROVAL_CHANGED]
    finally:
        release.set()
        reader.join(2)
        if requester.ident is not None:
            requester.join(2)
        engine.close()
