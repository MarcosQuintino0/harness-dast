"""Contratos da vigia de fontes do proxy."""

from threading import Event, Thread

from harness_dast.adapters.scope_proxy.decision import Reason
from harness_dast.adapters.scope_proxy.gate_watch import GateWatch


def test_snapshot_envelhecido_trava_mesmo_apos_nova_leitura() -> None:
    now = [0.0]
    watch = GateWatch(lambda: None, lambda: now[0])
    try:
        assert watch.check() is None
        now[0] = 0.201
        assert watch.check() is Reason.APPROVAL_CHANGED
        watch.run_once()
        assert watch.check() is Reason.APPROVAL_CHANGED
    finally:
        watch.close()


def test_leitura_bloqueada_nao_bloqueia_concessao_nem_encerramento() -> None:
    now = [0.0]
    entered = Event()
    release = Event()
    calls = [0]

    def detect() -> Reason | None:
        calls[0] += 1
        if calls[0] > 1:
            entered.set()
            release.wait()
        return None

    watch = GateWatch(detect, lambda: now[0])
    thread = Thread(target=watch.run_once, daemon=True)
    thread.start()
    try:
        assert entered.wait(2)
        now[0] = 0.201
        assert watch.check() is Reason.APPROVAL_CHANGED
        watch.close()
    finally:
        release.set()
        thread.join(2)
    assert watch.check() is Reason.APPROVAL_CHANGED


def test_inicializacao_com_fonte_invalida_fecha() -> None:
    watch = GateWatch(lambda: Reason.KILL_SWITCH, lambda: 0.0)
    try:
        assert watch.check() is Reason.KILL_SWITCH
    finally:
        watch.close()
