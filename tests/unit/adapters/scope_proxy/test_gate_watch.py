"""Contratos da vigia de fontes do proxy."""

import sys
from threading import Event, Lock, Thread

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


@pytest.fixture
def no_periodic_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Impede que a vigia periodica leia durante o teste (so a reverificacao le)."""
    monkeypatch.setattr(gate_watch_module, "_INTERVAL", 3600.0)


def test_snapshot_velho_so_concede_depois_de_reverificar(no_periodic_reads: None) -> None:
    now = [0.0]
    reads = [0]

    def detect() -> Reason | None:
        reads[0] += 1
        return None

    watch = GateWatch(detect, lambda: now[0])
    try:
        assert watch.check() is None
        before = reads[0]
        now[0] = 0.201
        assert watch.check() is None
        assert reads[0] > before
        assert watch.result is None
    finally:
        watch.close()


def test_thread_atrasada_nao_trava_e_concede_com_retrato_novo() -> None:
    now = [0.0]
    watch = GateWatch(lambda: None, lambda: now[0])
    try:
        for step in (0.3, 1.0, 5.0):
            now[0] += step
            assert watch.check() is None
    finally:
        watch.close()


def test_mudanca_real_na_reverificacao_trava(events: list[WatchCause]) -> None:
    now = [0.0]
    changed = [False]
    watch = GateWatch(
        lambda: Detection(Reason.APPROVAL_CHANGED, WatchCause.HASH) if changed[0] else None,
        lambda: now[0],
    )
    changed[0] = True
    now[0] = 0.5
    assert watch.check() is Reason.APPROVAL_CHANGED
    changed[0] = False
    now[0] = 0.5001
    assert watch.check() is Reason.APPROVAL_CHANGED
    watch.close()
    assert events == [WatchCause.HASH]


def test_erro_na_reverificacao_trava_sem_propagar(events: list[WatchCause]) -> None:
    now = [0.0]
    broken = [False]

    def detect() -> Reason | None:
        if broken[0]:
            raise OSError("valor sintetico confidencial")
        return None

    watch = GateWatch(detect, lambda: now[0])
    broken[0] = True
    now[0] = 0.5
    assert watch.check() is Reason.APPROVAL_CHANGED
    watch.close()
    assert events == [WatchCause.DETECT_ERROR]


@pytest.fixture
def slow_denials(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(gate_watch_module, "log_slow_deny", lambda: captured.append("slow"))
    return captured


def test_tempo_limite_da_reverificacao_nega_sem_travar(
    events: list[WatchCause], slow_denials: list[str]
) -> None:
    now = [0.0]
    entered = Event()
    release = Event()
    calls = [0]

    def detect() -> Reason | None:
        calls[0] += 1
        if calls[0] > 1:
            entered.set()
            release.wait(5)
        return None

    watch = GateWatch(detect, lambda: now[0], reverify_timeout=0.02)
    try:
        now[0] = 0.5
        assert watch.check() is Reason.APPROVAL_CHANGED
        assert entered.wait(2)
        release.set()
        granted = False
        for _ in range(200):
            if watch.check() is None:
                granted = True
                break
            Event().wait(0.01)
        assert granted
    finally:
        release.set()
        watch.close()
    assert events == [WatchCause.CLOSE]
    assert slow_denials


def test_reverificacao_lenta_nega_sem_travar_e_pedido_seguinte_concede(
    events: list[WatchCause], slow_denials: list[str]
) -> None:
    now = [0.0]
    slow = [True]

    def detect() -> Reason | None:
        if slow[0]:
            now[0] += 0.3  # a leitura leva mais que a idade maxima
        return None

    watch = GateWatch(detect, lambda: now[0])
    now[0] = 0.5
    assert watch.check() is Reason.APPROVAL_CHANGED
    slow[0] = False
    now[0] += 0.5
    assert watch.check() is None
    watch.close()
    assert events == [WatchCause.CLOSE]
    assert slow_denials == ["slow"]


def test_negacao_por_lentidao_registra_no_maximo_uma_linha_por_segundo(
    slow_denials: list[str],
) -> None:
    now = [0.0]
    slow = [True]

    def detect() -> Reason | None:
        if slow[0]:
            now[0] += 0.3
        return None

    watch = GateWatch(detect, lambda: now[0])
    try:
        now[0] = 0.5
        for _ in range(3):
            assert watch.check() is Reason.APPROVAL_CHANGED
        assert slow_denials == ["slow"]
        now[0] += 2.0
        assert watch.check() is Reason.APPROVAL_CHANGED
        assert slow_denials == ["slow", "slow"]
    finally:
        watch.close()


def test_diagnostico_de_lentidao_tem_so_evento_e_categoria(
    capfd: pytest.CaptureFixture[str],
) -> None:
    result = diagnostic.log_slow_deny()
    for _ in range(200):
        if result.status is not DiagnosticStatus.PENDING:
            break
        Event().wait(0.01)
    assert capfd.readouterr().err == '{"event": "gate_watch_slow_deny", "category": "slow_deny"}\n'


def test_encerramento_trava_mesmo_com_retrato_fresco(events: list[WatchCause]) -> None:
    watch = GateWatch(lambda: None, lambda: 0.0)
    assert watch.check() is None
    watch.close()
    assert watch.check() is Reason.APPROVAL_CHANGED
    assert events == [WatchCause.CLOSE]


def test_relogio_para_tras_trava_sem_reverificar(
    events: list[WatchCause], no_periodic_reads: None
) -> None:
    now = [5.0]
    reads = [0]

    def detect() -> Reason | None:
        reads[0] += 1
        return None

    watch = GateWatch(detect, lambda: now[0])
    before = reads[0]
    now[0] = 1.0
    assert watch.check() is Reason.APPROVAL_CHANGED
    assert reads[0] == before
    watch.close()
    assert events == [WatchCause.CLOCK]


def test_chamadas_concorrentes_compartilham_uma_reverificacao(no_periodic_reads: None) -> None:
    now = [0.0]
    entered = Event()
    release = Event()
    calls = [0]
    lock = Lock()

    def detect() -> Reason | None:
        with lock:
            calls[0] += 1
            number = calls[0]
        if number > 1:
            entered.set()
            release.wait(2)
        return None

    watch = GateWatch(detect, lambda: now[0], reverify_timeout=5.0)
    results: list[Reason | None] = []
    now[0] = 0.5
    threads = [Thread(target=lambda: results.append(watch.check())) for _ in range(6)]
    for thread in threads:
        thread.start()
    assert entered.wait(2)
    release.set()
    for thread in threads:
        thread.join(5)
    watch.close()
    assert results == [None] * 6
    assert calls[0] == 2  # partida + uma unica reverificacao compartilhada


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

    watch = GateWatch(detect, lambda: now[0], reverify_timeout=0.02)
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
        now[0] = -1.0
        assert watch.check() is Reason.APPROVAL_CHANGED
    else:
        watch.close()
    assert watch.result is not None
    assert watch.result.status is DiagnosticStatus.START_FAILED
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
        assert watch.result is not None
        assert watch.result.status is DiagnosticStatus.START_FAILED
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
        now[0] = -1.0
        assert watch.check() is Reason.APPROVAL_CHANGED
        assert entered.wait(2)
        assert watch.result is not None
        assert watch.result.status is DiagnosticStatus.PENDING
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

    def observed_emit(cause: WatchCause, result: DiagnosticResult, event: str) -> None:
        try:
            emit(cause, result, event)
        finally:
            completed.set()

    monkeypatch.setattr(sys, "stderr", BrokenStream())
    monkeypatch.setattr(diagnostic, "_emit", observed_emit)
    now[0] = -1.0
    assert watch.check() is Reason.APPROVAL_CHANGED
    assert completed.wait(2)
    assert watch.result is not None
    assert watch.result.status is DiagnosticStatus.WRITE_FAILED
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
