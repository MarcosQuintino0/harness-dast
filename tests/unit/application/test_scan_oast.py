"""`scan` com `scan.oast`: SSRF guiado pelo contrato, com o retorno observado (ADR 0100)."""

from typing import Any

from harness_dast.application.report import ReportRequest
from harness_dast.application.scan import ScanRequest
from harness_dast.domain.api_model import MediaBody, Operation, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.oast_ssrf import OastEvent, callback_url, make_token
from harness_dast.domain.scan_result import ScanResult
from tests.fakes.rig import agenda_flows, agenda_profile, agenda_spec
from tests.fakes.scan_rig import FakeOastBridge, ScanRig

SEED = 11  # FixedEntropy
TOKEN = make_token(SEED, "registrar", "body", "callback_url")


def _spec() -> Any:
    spec = agenda_spec()
    schema = Schema(
        type="object",
        properties={"nome": Schema(type="string"), "callback_url": Schema(type="string")},
        required=("nome", "callback_url"),
    )
    hook = Operation(
        operation_id="registrar",
        method="post",
        path="/api/ganchos",
        request_body=RequestBody(
            required=True, media=(MediaBody(media_type="application/json", body_schema=schema),)
        ),
    )
    return spec.model_copy(update={"operations": (*spec.operations, hook)})


class FakeOast:
    """`OastEvents` falso: devolve os eventos que o teste definiu."""

    def __init__(
        self, events: tuple[OastEvent, ...] = (), *, down: bool = False, lost: bool = False
    ) -> None:
        self.events = events
        self.down = down
        self.lost = lost
        self.baselines = 0
        self.reads = 0

    def oast_baseline(self) -> int:
        self.baselines += 1
        if self.down:
            raise ExternalToolError("ZAP fora do ar.")
        return 5

    def oast_events(self, since: int) -> tuple[OastEvent, ...]:
        assert since == 5
        if self.lost:
            raise ExternalToolError("observador indisponivel")
        self.reads += 1
        return self.events


def _scan(port: FakeOast | None, **scan: Any) -> tuple[ScanRig, ScanResult]:
    rig = ScanRig(spec=_spec(), flows=agenda_flows(), profile=agenda_profile(scan=scan))
    rig.run_probe()
    request = ScanRequest(product="agenda", run_id=rig.probe_result.run_id)
    return rig, rig.scan(oast=port).execute(request)


def _hook_requests(rig: ScanRig) -> list[Any]:
    return [r for r in rig.target.requests if r.url.endswith("/api/ganchos")]


def test_with_oast_the_callback_url_goes_in_the_field_and_the_return_becomes_an_alert() -> None:
    event = OastEvent(event_id=77, path=f"/{TOKEN}", at="2026-11-17T15:00:00+00:00")
    oast = FakeOast((event,))
    rig, result = _scan(oast, oast=True)

    sent = [r for r in _hook_requests(rig) if callback_url(TOKEN).encode() in (r.body or b"")]
    assert len(sent) == 1
    assert result.ssrf is not None
    assert (result.ssrf.planned, result.ssrf.observed, result.ssrf.events_seen) == (1, 1, 1)
    alerts = [a for a in rig.artifacts.alerts[result.run_id] if a["pluginId"] == "hdast-oast-ssrf"]
    assert len(alerts) == 1
    assert "77" in alerts[0]["evidence"]
    assert alerts[0]["param"] == "callback_url"
    audit = {e.operation_id for e in rig.store.audit[result.run_id]}
    assert "oast:registrar" in audit


def test_the_observed_return_becomes_a_finding_of_the_operation_in_the_report() -> None:
    event = OastEvent(event_id=77, path=f"/{TOKEN}")
    rig, result = _scan(FakeOast((event,)), oast=True)

    report = rig.report().execute(ReportRequest(product="agenda", run_id=result.run_id)).report

    found = [f for f in report.findings if f.plugin_id == "hdast-oast-ssrf"]
    assert len(found) == 1
    assert (found[0].operation_id, found[0].proposed_severity) == ("registrar", "high")
    assert found[0].classification.cwe == 918
    assert found[0].parameter == "callback_url"


def test_without_a_return_the_request_is_sent_but_nothing_is_reported() -> None:
    oast = FakeOast(())
    rig, result = _scan(oast, oast=True)

    assert result.ssrf is not None
    assert (result.ssrf.sent, result.ssrf.observed) == (1, 0)
    assert not [
        a for a in rig.artifacts.alerts[result.run_id] if a["pluginId"] == "hdast-oast-ssrf"
    ]
    assert oast.reads >= 10  # esperou o prazo inteiro do retorno


def test_with_the_key_off_there_is_no_oast_traffic_no_policy_change_and_no_summary() -> None:
    oast = FakeOast((OastEvent(event_id=1, path=f"/{TOKEN}"),))
    rig, result = _scan(oast)

    assert result.ssrf is None
    assert result.policy.oast is False
    assert result.policy.oast_rules == ()
    assert (oast.baselines, oast.reads) == (0, 0)
    assert not any(callback_url(TOKEN).encode() in (r.body or b"") for r in rig.target.requests)
    assert not any(r.operation_id.startswith("oast:") for r in rig.target.requests)


def test_with_the_key_on_but_no_oast_port_the_step_does_not_run() -> None:
    rig, result = _scan(None, oast=True)

    assert result.ssrf is None
    assert _hook_requests(rig) == [] or all(
        b"oast-gateway" not in (r.body or b"") for r in _hook_requests(rig)
    )


def test_a_method_the_approved_scope_does_not_allow_is_not_sent() -> None:
    rig = ScanRig(spec=_spec(), flows=agenda_flows(), profile=agenda_profile(scan={"oast": True}))
    rig.run_probe()
    stored = rig.profiles.load("agenda")
    base = stored.scope.allow[0]
    read_only = base.model_copy(update={"paths": ("/api/ganchos",), "methods": ("GET",)})
    rest = base.model_copy(update={"paths": ("/api/pacientes/**", "/api/auth/**", "/api/saude")})
    scope = stored.scope.model_copy(update={"allow": (rest, read_only)})
    rig.profiles.add(stored.model_copy(update={"scope": scope}), existing_files={"./openapi.json"})
    oast = FakeOast(())

    result = rig.scan(oast=oast).execute(
        ScanRequest(product="agenda", run_id=rig.probe_result.run_id)
    )

    assert result.ssrf is not None
    assert result.ssrf.sent == 0
    assert [(s.operation_id, s.reason) for s in result.ssrf.skipped] == [
        ("registrar", "method_not_allowed")
    ]
    assert oast.baselines == 2


def test_when_the_return_service_is_down_nothing_is_sent_and_the_scan_goes_on() -> None:
    oast = FakeOast((), down=True)
    rig, result = _scan(oast, oast=True)

    assert result.status == "completed"
    assert result.ssrf is None
    assert result.oast_verification is not None
    assert result.oast_verification.ssrf == "unverifiable"
    assert result.oast_verification.reason is not None
    assert not result.policy.oast
    assert not any(b"oast-gateway" in (r.body or b"") for r in _hook_requests(rig))


def test_without_the_probe_exchanges_the_step_is_skipped_and_the_scan_goes_on() -> None:
    rig = ScanRig(spec=_spec(), flows=agenda_flows(), profile=agenda_profile(scan={"oast": True}))
    rig.run_probe()
    rig.store.exchanges.clear()
    oast = FakeOast(())

    result = rig.scan(oast=oast).execute(
        ScanRequest(product="agenda", run_id=rig.probe_result.run_id)
    )

    assert result.status == "completed"
    assert result.ssrf is None
    assert oast.baselines == 2


def test_ponte_ausente_desliga_regras_e_informa_lacuna() -> None:
    rig = ScanRig(spec=_spec(), flows=agenda_flows(), profile=agenda_profile(scan={"oast": True}))
    rig.run_probe()
    scan = rig.scan(oast=FakeOast(), bridge=FakeOastBridge(available=False))
    result = scan.execute(ScanRequest(product="agenda", run_id=rig.probe_result.run_id))
    report = rig.report().execute(ReportRequest(product="agenda", run_id=result.run_id)).report

    assert result.oast_verification is not None
    assert result.oast_verification.zap == result.oast_verification.ssrf == "unverifiable"
    assert not result.policy.oast
    assert result.ssrf is None
    assert report.coverage.partial
    assert report.coverage.oast_gap
    assert not any(b"oast-gateway" in (r.body or b"") for r in _hook_requests(rig))


def test_ponte_desconhecida_nao_e_tratada_como_disponivel() -> None:
    rig = ScanRig(spec=_spec(), flows=agenda_flows(), profile=agenda_profile(scan={"oast": True}))
    rig.run_probe()
    scan = rig.scan(oast=FakeOast(), bridge=FakeOastBridge(available=None))
    result = scan.execute(ScanRequest(product="agenda", run_id=rig.probe_result.run_id))
    assert result.oast_verification is not None
    assert result.oast_verification.zap == "unverifiable"
    assert not result.policy.oast


def test_queda_apos_envio_deixa_ssrf_nao_verificavel() -> None:
    _, result = _scan(FakeOast(lost=True), oast=True)
    assert result.oast_verification is not None
    assert result.oast_verification.ssrf == "unverifiable"
    assert result.ssrf is not None
    assert result.ssrf.sent == 1


def test_artefato_legado_com_oast_e_lacuna_desconhecida() -> None:
    from harness_dast.domain.oast_verification import oast_gap

    _, result = _scan(FakeOast(), oast=True)
    legacy = result.model_copy(update={"oast_verification": None})
    assert oast_gap(legacy) is not None


def test_callback_nao_configurado_desliga_oast_e_registra_lacuna() -> None:
    rig = ScanRig(spec=_spec(), flows=agenda_flows(), profile=agenda_profile(scan={"oast": True}))
    rig.run_probe()
    rig.zap.oast_config_unavailable = True

    result = rig.scan(oast=FakeOast()).execute(
        ScanRequest(product="agenda", run_id=rig.probe_result.run_id)
    )

    assert result.status == "completed"
    assert result.oast_verification is not None
    assert result.oast_verification.zap == "unverifiable"
    assert result.oast_verification.ssrf == "unverifiable"
    assert result.oast_verification.reason is not None
    assert "Callback" in result.oast_verification.reason
    assert not result.policy.oast
    assert not any(b"oast-gateway" in (r.body or b"") for r in _hook_requests(rig))


def test_lacuna_da_ponte_aparece_no_relatorio_e_no_painel() -> None:
    from harness_dast.domain.panel.build_content import _scan_items
    from harness_dast.domain.report.html import render_html
    from harness_dast.domain.report.markdown import render_markdown

    rig = ScanRig(spec=_spec(), flows=agenda_flows(), profile=agenda_profile(scan={"oast": True}))
    rig.run_probe()
    result = rig.scan(oast=FakeOast(), bridge=FakeOastBridge(available=False)).execute(
        ScanRequest(product="agenda", run_id=rig.probe_result.run_id)
    )
    report = rig.report().execute(ReportRequest(product="agenda", run_id=result.run_id)).report

    assert result.oast_verification is not None
    reason = result.oast_verification.reason
    assert reason is not None
    assert reason in render_markdown(report)
    assert reason in render_html(report)
    assert any(reason in item.text for item in _scan_items(result))


def test_leitura_de_json_legado_oast_assinala_estado_desconhecido() -> None:
    import json

    from harness_dast.domain.oast_verification import oast_gap

    _, result = _scan(FakeOast(), oast=True)
    data = result.model_dump(mode="json")
    data.pop("oast_verification")
    legacy = ScanResult.model_validate_json(json.dumps(data))

    assert oast_gap(legacy) is not None
