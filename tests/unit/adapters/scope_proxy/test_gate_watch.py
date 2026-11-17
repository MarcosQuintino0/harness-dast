"""Contratos da vigia de fontes do proxy."""

from threading import Event, Thread

import pytest

import harness_dast.adapters.scope_proxy.gate_watch as gate_watch_module
import harness_dast.adapters.scope_proxy.watch_diagnostic as diagnostic
from harness_dast.adapters.scope_proxy.decision import Reason
from harness_dast.adapters.scope_proxy.gate_watch import GateWatch
from harness_dast.adapters.scope_proxy.watch_diagnostic import Detection, WatchCause


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


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[WatchCause]:
    captured: list[WatchCause] = []
    monkeypatch.setattr(gate_watch_module, "log_latch", captured.append)
    return captured


def test_evento_de_idade_ocorre_so_na_primeira_trava(events: list[WatchCause]) -> None:
    now = [0.0]
    watch = GateWatch(lambda: None, lambda: now[0])
    now[0] = 0.201
    assert watch.check() is Reason.APPROVAL_CHANGED
    watch.run_once()
    watch.close()
    assert events == [WatchCause.AGE]


@pytest.mark.parametrize(
    ("reading", "category"),
    [
        (Reason.KILL_SWITCH, WatchCause.DETECT_DENIED),
        (Detection(Reason.APPROVAL_CHANGED, WatchCause.HASH), WatchCause.HASH),
    ],
)
def test_evento_reflete_negacao_verificada(
    events: list[WatchCause], reading: Reason | Detection, category: WatchCause
) -> None:
    watch = GateWatch(lambda: reading, lambda: 0.0)
    assert watch.check() is (reading.reason if isinstance(reading, Detection) else reading)
    watch.close()
    assert events == [category]


def test_evento_de_relogio_retrocedido_nao_expoe_valor(events: list[WatchCause]) -> None:
    now = [1.0]
    watch = GateWatch(lambda: None, lambda: now[0])
    now[0] = 0.0
    assert watch.check() is Reason.APPROVAL_CHANGED
    watch.close()
    assert events == [WatchCause.CLOCK]


def test_encerramento_emite_somente_um_evento(events: list[WatchCause]) -> None:
    watch = GateWatch(lambda: None, lambda: 0.0)
    watch.close()
    watch.close()
    assert watch.check() is Reason.APPROVAL_CHANGED
    assert events == [WatchCause.CLOSE]


def test_log_estruturado_contem_somente_categoria(caplog: pytest.LogCaptureFixture) -> None:
    diagnostic._emit(WatchCause.ACCESS)
    assert [record.getMessage() for record in caplog.records] == [
        '{"event": "gate_watch_latch", "category": "access"}'
    ]


def test_emissao_bloqueada_nao_bloqueia_encerramento(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = Event()
    release = Event()

    def blocked(cause: WatchCause) -> None:
        entered.set()
        release.wait()

    monkeypatch.setattr(diagnostic, "_emit", blocked)
    watch = GateWatch(lambda: None, lambda: 0.0)
    try:
        watch.close()
        assert entered.wait(2)
        assert watch.check() is Reason.APPROVAL_CHANGED
    finally:
        release.set()


def test_excecao_da_verificacao_registra_categoria_sem_mensagem(
    events: list[WatchCause],
) -> None:
    broken = [False]

    def detect() -> Reason | None:
        if broken[0]:
            raise OSError("valor sintetico confidencial")
        return None

    watch = GateWatch(detect, lambda: 0.0)
    broken[0] = True
    with pytest.raises(OSError, match="valor sintetico confidencial"):
        watch.run_once()
    assert watch.check() is Reason.APPROVAL_CHANGED
    watch.close()
    assert events == [WatchCause.DETECT_ERROR]
