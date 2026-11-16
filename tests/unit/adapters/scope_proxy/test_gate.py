from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from harness_dast.adapters.scope_proxy.decision import Reason
from harness_dast.adapters.scope_proxy.gate import RunGate

START = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


class FakeNow:
    def __init__(self) -> None:
        self.value = START

    def __call__(self) -> datetime:
        return self.value


def make(tmp_path: Path) -> tuple[RunGate, FakeNow, Path]:
    now = FakeNow()
    flag = tmp_path / "KILL"
    gate = RunGate(kill_flag=flag, deadline=START + timedelta(minutes=30), now=now)
    return gate, now, flag


def test_check_permite_antes_do_prazo_e_sem_arquivo_sinal(tmp_path: Path) -> None:
    gate, _, _ = make(tmp_path)

    assert gate.check().allowed is True


def test_check_nega_assim_que_o_arquivo_sinal_aparece(tmp_path: Path) -> None:
    gate, _, flag = make(tmp_path)
    assert gate.check().allowed is True

    flag.touch()
    verdict = gate.check()

    assert verdict.allowed is False
    assert verdict.reason is Reason.KILL_SWITCH


def test_check_continua_negando_depois_que_o_arquivo_sinal_e_removido(tmp_path: Path) -> None:
    # A trava é travada de propósito: apagar o arquivo não reabre a saída.
    gate, _, flag = make(tmp_path)
    flag.touch()
    assert gate.check().allowed is False

    flag.unlink()

    assert gate.check().reason is Reason.KILL_SWITCH


def test_check_nega_no_instante_do_prazo(tmp_path: Path) -> None:
    gate, now, _ = make(tmp_path)
    now.value = START + timedelta(minutes=30) - timedelta(microseconds=1)
    assert gate.check().allowed is True

    now.value = START + timedelta(minutes=30)
    verdict = gate.check()

    assert verdict.allowed is False
    assert verdict.reason is Reason.RUN_EXPIRED


def test_check_continua_negando_se_o_relogio_voltar(tmp_path: Path) -> None:
    gate, now, _ = make(tmp_path)
    now.value = START + timedelta(hours=1)
    assert gate.check().allowed is False

    now.value = START

    assert gate.check().reason is Reason.RUN_EXPIRED


def test_check_prefere_a_trava_quando_prazo_e_sinal_coincidem(tmp_path: Path) -> None:
    gate, now, flag = make(tmp_path)
    flag.touch()
    now.value = START + timedelta(hours=2)

    assert gate.check().reason is Reason.KILL_SWITCH


def test_mark_audit_failure_trava_tudo(tmp_path: Path) -> None:
    gate, _, _ = make(tmp_path)

    gate.mark_audit_failure()

    assert gate.check().reason is Reason.AUDIT_FAILURE


def test_check_trava_se_nao_consegue_verificar_o_arquivo_sinal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Falha de E/S ao consultar o sinal é difícil de provocar de verdade; sem saber se a
    # trava foi acionada, a resposta segura é travar.
    def fail(self: Path) -> bool:
        raise PermissionError("negado")

    gate, _, _ = make(tmp_path)
    monkeypatch.setattr(Path, "lstat", fail)

    assert gate.check().reason is Reason.KILL_SWITCH
