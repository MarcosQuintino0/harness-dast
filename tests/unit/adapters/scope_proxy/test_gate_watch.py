"""Contratos da vigia de fontes do proxy."""

import sys
from threading import Event, Thread

import pytest

import harness_dast.adapters.scope_proxy.gate_watch as gate_watch_module
import harness_dast.adapters.scope_proxy.watch_diagnostic as diagnostic
from harness_dast.adapters.scope_proxy.decision import Reason
from harness_dast.adapters.scope_proxy.gate_watch import GateWatch
from harness_dast.adapters.scope_proxy.watch_diagnostic import (
    Detection,
    DiagnosticResult,
    DiagnosticStatus,
    WatchCause,
)


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


def test_log_estruturado_contem_somente_categoria(capfd: pytest.CaptureFixture[str]) -> None:
    result = DiagnosticResult()
    diagnostic._emit(WatchCause.ACCESS, result)
    assert capfd.readouterr().err == '{"event": "gate_watch_latch", "category": "access"}\n'
    assert result.status is DiagnosticStatus.SENT


def test_emissao_bloqueada_nao_bloqueia_encerramento(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = Event()
    release = Event()

    class BlockedStream:
        def write(self, payload: str) -> int:
            entered.set()
            release.wait()
            return len(payload)

        def flush(self) -> None:
            pass

    monkeypatch.setattr(sys, "stderr", BlockedStream())
    watch = GateWatch(lambda: None, lambda: 0.0)
    try:
        watch.close()
        assert entered.wait(2)
        assert watch.check() is Reason.APPROVAL_CHANGED
    finally:
        release.set()


@pytest.mark.parametrize("action", ["check", "close"])
def test_falha_de_iniciar_diagnostico_preserva_trava(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], action: str
) -> None:
    now = [0.0]
    watch = GateWatch(lambda: None, lambda: now[0])

    class FailedThread:
        def start(self) -> None:
            raise RuntimeError("dado sintetico confidencial")

    monkeypatch.setattr(diagnostic, "Thread", lambda **kwargs: FailedThread())
    if action == "check":
        now[0] = 0.201
        assert watch.check() is Reason.APPROVAL_CHANGED
    else:
        watch.close()
    assert watch.diagnostic is not None
    assert watch.diagnostic.status is DiagnosticStatus.START_FAILED
    assert watch.check() is Reason.APPROVAL_CHANGED
    watch.close()
    assert capfd.readouterr().err == ""


def test_falha_de_iniciar_diagnostico_na_partida_preserva_motivo(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    class FailedThread:
        def start(self) -> None:
            raise RuntimeError("dado sintetico confidencial")

    monkeypatch.setattr(diagnostic, "Thread", lambda **kwargs: FailedThread())
    watch = GateWatch(lambda: Reason.KILL_SWITCH, lambda: 0.0)
    try:
        assert watch.check() is Reason.KILL_SWITCH
        assert watch.diagnostic is not None
        assert watch.diagnostic.status is DiagnosticStatus.START_FAILED
    finally:
        watch.close()
    assert capfd.readouterr().err == ""


def test_emissor_bloqueado_nao_bloqueia_recusa(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = Event()
    release = Event()
    now = [0.0]

    class BlockedStream:
        def write(self, payload: str) -> int:
            entered.set()
            release.wait()
            return len(payload)

        def flush(self) -> None:
            pass

    watch = GateWatch(lambda: None, lambda: now[0])
    monkeypatch.setattr(sys, "stderr", BlockedStream())
    try:
        now[0] = 0.201
        assert watch.check() is Reason.APPROVAL_CHANGED
        assert entered.wait(2)
        assert watch.diagnostic is not None
        assert watch.diagnostic.status is DiagnosticStatus.PENDING
        assert watch.check() is Reason.APPROVAL_CHANGED
    finally:
        release.set()
        watch.close()


def test_falha_de_emissor_preserva_recusa_sem_traceback(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    now = [0.0]
    watch = GateWatch(lambda: None, lambda: now[0])
    completed = Event()
    emit = diagnostic._emit

    class BrokenStream:
        def write(self, payload: str) -> int:
            raise OSError("dado sintetico confidencial")

        def flush(self) -> None:
            pass

    def observed_emit(cause: WatchCause, result: DiagnosticResult) -> None:
        try:
            emit(cause, result)
        finally:
            completed.set()

    monkeypatch.setattr(sys, "stderr", BrokenStream())
    monkeypatch.setattr(diagnostic, "_emit", observed_emit)
    now[0] = 0.201
    assert watch.check() is Reason.APPROVAL_CHANGED
    assert completed.wait(2)
    assert watch.diagnostic is not None
    assert watch.diagnostic.status is DiagnosticStatus.WRITE_FAILED
    watch.close()
    assert watch.check() is Reason.APPROVAL_CHANGED
    assert capfd.readouterr().err == ""


def test_escrita_parcial_do_diagnostico_indica_falha(monkeypatch: pytest.MonkeyPatch) -> None:
    result = DiagnosticResult()

    class ShortStream:
        def write(self, payload: str) -> int:
            return 1

        def flush(self) -> None:
            pass

    monkeypatch.setattr(sys, "stderr", ShortStream())
    diagnostic._emit(WatchCause.ACCESS, result)
    assert result.status is DiagnosticStatus.WRITE_FAILED


def test_falha_de_flush_do_diagnostico_e_observavel(monkeypatch: pytest.MonkeyPatch) -> None:
    result = DiagnosticResult()

    class BrokenFlush:
        def write(self, payload: str) -> int:
            return len(payload)

        def flush(self) -> None:
            raise ValueError("dado sintetico confidencial")

    monkeypatch.setattr(sys, "stderr", BrokenFlush())
    diagnostic._emit(WatchCause.ACCESS, result)
    assert result.status is DiagnosticStatus.WRITE_FAILED


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
