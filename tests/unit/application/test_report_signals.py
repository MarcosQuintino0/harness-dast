"""`report` com os sinais de erro interno vistos pela cerca (ADR 0049)."""

from datetime import timedelta

import pytest

from harness_dast.application.report import Report, ReportRequest
from harness_dast.domain.api_model import ApiSpec, Operation
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.signal_findings import parse_instant
from harness_dast.domain.signal_result import DISABLED_MESSAGE
from harness_dast.domain.traffic import ProxyRow
from tests.fakes.probe_ports import InMemorySpecs
from tests.fakes.rig import agenda_flows
from tests.fakes.scan_ports import FakeProxyAudit
from tests.fakes.scan_rig import ScanRig


def scanned() -> ScanRig:
    rig = ScanRig(flows=agenda_flows())
    rig.run_probe()
    rig.run_scan()
    return rig


def request(rig: ScanRig, **changes: object) -> ReportRequest:
    return ReportRequest(product="agenda", run_id=rig.probe_result.run_id, **changes)  # type: ignore[arg-type]  # dict heterogêneo de teste


def rows_for(rig: ScanRig, *, offset: timedelta = timedelta(seconds=1)) -> tuple[ProxyRow, ...]:
    started = parse_instant(rig.probe_result.started_at)
    assert started is not None
    at = started + offset

    def make(
        path: str,
        status: int,
        signals: tuple[str, ...] = (),
        skip: str | None = None,
    ) -> ProxyRow:
        return ProxyRow(
            at=at,
            decision="allow",
            reason="allowed",
            method="GET",
            path=path,
            status=status,
            signals=signals,
            signal_skip=skip,
        )

    return (
        make("/api/pacientes/7", 500, ("sql_error",)),
        make("/api/pacientes/8", 500, ("sql_error",)),
        make("/api/pacientes/9", 200),
        make("/api/x.png", 200, skip="type"),
    )


def test_report_le_a_auditoria_grava_o_artefato_e_monta_os_achados_de_sinal() -> None:
    rig = scanned()

    outcome = rig.report(proxy_audit=FakeProxyAudit(rows_for(rig))).execute(request(rig))

    signals = outcome.report.proxy_signals
    assert signals is not None
    assert signals.enabled
    assert (signals.responses_examined, signals.responses_skipped) == (3, {"type": 1})
    assert signals.counts["sql_error"] == 2
    (finding,) = signals.findings
    assert (finding.operation_id, finding.path_template) == ("buscar", "/api/pacientes/{}")
    assert rig.artifacts.signals[rig.probe_result.run_id] == signals
    assert outcome.report.summary.signal_by_severity["medium"] == 1
    assert outcome.report.summary.total == 0


def test_achado_de_sinal_conta_no_gate_de_severidade() -> None:
    rig = scanned()
    audit = FakeProxyAudit(rows_for(rig))

    medium = rig.report(proxy_audit=audit).execute(request(rig, fail_on="medium"))
    high = rig.report(proxy_audit=audit).execute(request(rig, fail_on="high"))
    off = rig.report(proxy_audit=audit).execute(request(rig, fail_on="none"))

    assert [o.exceeds_threshold for o in (medium, high, off)] == [True, False, False]


def test_achado_de_sinal_nao_some_com_a_triagem_e_o_gate_nao_depende_dela() -> None:
    rig = scanned()
    audit = FakeProxyAudit(rows_for(rig))
    rig.artifacts.triage[rig.probe_result.run_id] = {"schema_version": 1, "annotations": []}

    outcome = rig.report(proxy_audit=audit).execute(request(rig, fail_on="medium"))

    assert outcome.exceeds_threshold is True


def test_sem_auditoria_reaproveita_o_error_signals_que_ja_existe() -> None:
    rig = scanned()
    first = rig.report(proxy_audit=FakeProxyAudit(rows_for(rig))).execute(request(rig))

    again = rig.report().execute(request(rig))

    assert again.report.proxy_signals == first.report.proxy_signals
    assert again.report.proxy_signals is not None
    assert again.report.proxy_signals.findings


def test_sem_auditoria_e_sem_arquivo_fica_desligado_com_a_mensagem() -> None:
    rig = scanned()

    outcome = rig.report().execute(request(rig))

    signals = outcome.report.proxy_signals
    assert signals is not None
    assert signals.enabled is False
    assert signals.message == DISABLED_MESSAGE
    assert rig.artifacts.signals == {}
    assert outcome.report.summary.signal_by_severity == {}


def test_linhas_fora_da_janela_nao_contam_e_o_resultado_fica_desligado() -> None:
    rig = scanned()
    before = rows_for(rig, offset=-timedelta(hours=2))

    outcome = rig.report(proxy_audit=FakeProxyAudit(before)).execute(request(rig))

    assert outcome.report.proxy_signals is not None
    assert outcome.report.proxy_signals.enabled is False
    assert rig.artifacts.signals == {}


def test_auditoria_ilegivel_nao_derruba_o_report() -> None:
    rig = scanned()
    audit = FakeProxyAudit(error=ConfigError("A trilha de auditoria do proxy está ilegível."))

    outcome = rig.report(proxy_audit=audit).execute(request(rig))

    assert outcome.report.proxy_signals is not None
    assert outcome.report.proxy_signals.enabled is False


def test_auditoria_ilegivel_com_arquivo_anterior_reaproveita_o_arquivo() -> None:
    rig = scanned()
    first = rig.report(proxy_audit=FakeProxyAudit(rows_for(rig))).execute(request(rig))
    broken = FakeProxyAudit(error=ConfigError("ilegível"))

    again = rig.report(proxy_audit=broken).execute(request(rig))

    assert again.report.proxy_signals == first.report.proxy_signals


def test_arquivo_error_signals_ilegivel_nao_derruba_o_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = scanned()

    def unreadable(run_id: str) -> None:
        raise ConfigError("O arquivo error-signals.json está ilegível.")

    monkeypatch.setattr(rig.artifacts, "read_signals", unreadable)

    outcome = rig.report().execute(request(rig))

    assert outcome.report.proxy_signals is not None
    assert outcome.report.proxy_signals.enabled is False


def test_o_report_nao_envia_nada_ao_alvo_nem_ao_zap_ao_ler_os_sinais() -> None:
    rig = scanned()
    sent, calls = len(rig.target.requests), list(rig.zap.calls)

    rig.report(proxy_audit=FakeProxyAudit(rows_for(rig))).execute(request(rig))

    assert len(rig.target.requests) == sent
    assert rig.zap.calls == calls


def test_findings_json_traz_proxy_signals_sem_nenhum_texto_de_corpo() -> None:
    rig = scanned()

    outcome = rig.report(proxy_audit=FakeProxyAudit(rows_for(rig))).execute(request(rig))

    text = outcome.report.model_dump_json()
    assert '"proxy_signals"' in text
    assert "ORA-" not in text


def test_report_resolve_operacao_do_contrato_ausente_do_probe() -> None:
    rig = scanned()
    operation = Operation(operation_id="extra", method="get", path="/extra/{id}")
    spec = rig.spec.model_copy(update={"operations": (*rig.spec.operations, operation)})
    old = rows_for(rig)[0]
    audit = FakeProxyAudit((old.model_copy(update={"path": "/extra/valor-alterado"}),))
    report = Report(
        profiles=rig.profiles,
        artifacts=rig.artifacts,
        sinks=[rig.sink],
        clock=rig.clock,
        harness_version="teste",
        proxy_audit=audit,
        specs=InMemorySpecs(spec),
    )

    result = report.execute(request(rig)).report.proxy_signals

    assert result is not None
    assert result.findings[0].operation_id == "extra"


def test_spec_divergente_preserva_modelos_historicos_do_probe() -> None:
    rig = scanned()
    spec = rig.spec.model_copy(update={"operations": ()})
    report = Report(
        profiles=rig.profiles,
        artifacts=rig.artifacts,
        sinks=[rig.sink],
        clock=rig.clock,
        harness_version="teste",
        proxy_audit=FakeProxyAudit(rows_for(rig)),
        specs=InMemorySpecs(spec),
    )

    signals = report.execute(request(rig)).report.proxy_signals

    assert signals is not None
    assert signals.findings[0].operation_id == "buscar"


def test_spec_ilegivel_preserva_modelos_historicos_do_probe() -> None:
    rig = scanned()

    class BrokenSpecs:
        def load(self, product: str, profile: ProductProfile) -> ApiSpec:
            raise ConfigError("OpenAPI ilegível")

    report = Report(
        profiles=rig.profiles,
        artifacts=rig.artifacts,
        sinks=[rig.sink],
        clock=rig.clock,
        harness_version="teste",
        proxy_audit=FakeProxyAudit(rows_for(rig)),
        specs=BrokenSpecs(),
    )
    signals = report.execute(request(rig)).report.proxy_signals

    assert signals is not None
    assert signals.findings[0].operation_id == "buscar"
