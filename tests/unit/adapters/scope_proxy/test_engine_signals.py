"""O sinal de erro interno só observa: nunca muda a decisão de escopo (ADR 0049)."""

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import harness_dast.adapters.scope_proxy.decision as decision
import harness_dast.adapters.scope_proxy.gate as gate
import harness_dast.adapters.scope_proxy.ratelimit as ratelimit
from harness_dast.adapters.scope_proxy.decision import ALLOW, Reason
from harness_dast.adapters.scope_proxy.engine import ScopeProxyEngine
from harness_dast.adapters.scope_proxy.signals import SignalReading, read_response_signals
from tests.unit.adapters.scope_proxy.helpers import make_policy

START = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
INSIDE = "https://api.exemplo.com/api/users"
OUTSIDE = "https://api.exemplo.com/api/admin/x"


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.audit = io.StringIO()
        self.engine = ScopeProxyEngine(
            make_policy(),
            policy_dir=tmp_path,
            audit_file=self.audit,
            stdout=io.StringIO(),
            now=lambda: START,
            monotonic=lambda: 1000.0,
        )

    def verdict(self, url: str) -> Reason:
        return self.engine.check_request(
            method="GET", url=url, host_header="api.exemplo.com", wants_upgrade=False
        ).reason

    def lines(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.audit.getvalue().splitlines()]

    def log_allowed(self, reading: SignalReading) -> None:
        self.engine.log(
            method="GET",
            url=INSIDE,
            scheme="https",
            at=START,
            host="api.exemplo.com",
            port=443,
            raw_path="/api/users",
            raw_query="",
            verdict=ALLOW,
            status=500,
            size=10,
            signals=reading.categories,
            signal_skip=reading.skipped,
        )


def test_resposta_liberada_com_sinal_grava_a_categoria_e_continua_liberada(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path)

    assert rig.verdict(INSIDE) is Reason.ALLOWED
    rig.log_allowed(SignalReading(categories=("sql_error",)))

    (line,) = rig.lines()
    assert line["signals"] == ["sql_error"]
    assert line["decision"] == "allow"
    assert rig.verdict(INSIDE) is Reason.ALLOWED


def test_sinal_gravado_nao_muda_nenhuma_decisao_de_escopo(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    before = (rig.verdict(INSIDE), rig.verdict(OUTSIDE))

    rig.log_allowed(SignalReading(categories=("sql_error", "stack_trace_java", "debug_page")))
    rig.log_allowed(SignalReading(skipped="error"))

    assert (rig.verdict(INSIDE), rig.verdict(OUTSIDE)) == before
    assert before == (Reason.ALLOWED, Reason.DENY_PATH)


def test_falha_da_leitura_nao_nega_e_a_linha_de_auditoria_sai_igual(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    def broken(*_: object) -> SignalReading:
        raise RuntimeError("defeito simulado")

    reading = read_response_signals("GET", 500, {}, b"x", inspect=broken)
    rig.log_allowed(reading)

    (line,) = rig.lines()
    assert line["decision"] == "allow"
    assert line["signal_skip"] == "error"
    assert "signals" not in line
    assert rig.verdict(INSIDE) is Reason.ALLOWED


def test_linha_negada_nao_leva_sinal_nem_motivo_de_pulo(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    denied = rig.engine.check_request(
        method="GET", url=OUTSIDE, host_header="api.exemplo.com", wants_upgrade=False
    )

    rig.engine.log(
        method="GET",
        url=OUTSIDE,
        scheme="https",
        at=START,
        host="api.exemplo.com",
        port=443,
        raw_path="/api/admin/x",
        raw_query="",
        verdict=denied,
        status=403,
        signals=("sql_error",),
        signal_skip="type",
    )

    (line,) = rig.lines()
    assert line["decision"] == "deny"
    assert "signals" not in line
    assert "signal_skip" not in line


def test_modulos_que_decidem_nao_conhecem_a_leitura_de_sinais() -> None:
    for module in (decision, gate, ratelimit):
        source = Path(module.__file__ or "").read_text(encoding="utf-8")
        assert "signal" not in source
