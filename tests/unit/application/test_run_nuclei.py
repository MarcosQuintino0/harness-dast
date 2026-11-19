"""`run` com o estágio `nuclei` (ADR 0122): ordem, chaves que só reduzem, falha, gate e resumo."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from harness_dast.application.authz.service import AuthzRequest
from harness_dast.application.negative import NegativeRequest
from harness_dast.application.nuclei import NucleiRequest
from harness_dast.application.preflight_report import PreflightReport
from harness_dast.application.probe import ProbeRequest
from harness_dast.application.report import ReportOutcome, ReportRequest
from harness_dast.application.run import RunPipeline, RunRequest, RunResult
from harness_dast.application.scan import ScanRequest
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.errors import ConfigError, ExitCode, ExternalToolError
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scan_result import ScanResult
from tests.fakes.clock import FixedClock, utc
from tests.fakes.nuclei import nuclei_finding, nuclei_result
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.unit.application.test_run import RUN_ID, Kill, Sink, _outcome, _preflight, _probe, _scan
from tests.unit.application.test_run_authz import _authz
from tests.unit.application.test_run_negative import _negative


def _profile(*, nuclei: bool = True, fail_on: str = "none") -> ProductProfile:
    data: dict[str, Any] = valid_profile_data("demo")
    data["extra_checks"] = {"nuclei": nuclei}
    data["scan"] = {"fail_on": fail_on}
    return ProductProfile.from_data(data)


@dataclass
class Rig:
    clock: FixedClock = field(default_factory=lambda: FixedClock(utc(2026, 11, 13, 10)))
    kill: Kill = field(default_factory=Kill)
    sink: Sink = field(default_factory=Sink)
    calls: list[str] = field(default_factory=list)
    nuclei_requests: list[NucleiRequest] = field(default_factory=list)
    profile_nuclei: bool = True
    fail_on: str = "none"
    wire_nuclei: bool = True
    exceeds_report: bool = False
    nuclei: Callable[[], NucleiResult] = field(default=lambda: nuclei_result())
    nuclei_error: Exception | None = None
    scan: Callable[[], ScanResult] = _scan
    authz: Callable[[], AuthzResult] = _authz
    negative: Callable[[], NegativeResult] = _negative

    def run(self, request: RunRequest) -> RunResult:
        profiles = InMemoryProfileRepository()
        profiles.add(_profile(nuclei=self.profile_nuclei, fail_on=self.fail_on))
        rig = self

        class _Pre:
            def execute(self, product: str) -> PreflightReport:
                rig.calls.append("preflight")
                return _preflight()

        class _Probe:
            def execute(self, request: ProbeRequest) -> ProbeResult:
                rig.calls.append("probe")
                rig.clock.advance_to(rig.clock.now() + timedelta(seconds=90))
                return _probe()

        class _Scan:
            def execute(self, request: ScanRequest) -> ScanResult:
                rig.calls.append("scan")
                return rig.scan()

        class _Nuclei:
            def execute(self, request: NucleiRequest) -> NucleiResult:
                rig.calls.append("nuclei")
                rig.nuclei_requests.append(request)
                if rig.nuclei_error is not None:
                    raise rig.nuclei_error
                return rig.nuclei()

        class _Authz:
            def execute(self, request: AuthzRequest) -> AuthzResult:
                rig.calls.append("authz")
                return rig.authz()

        class _Negative:
            def execute(self, request: NegativeRequest) -> NegativeResult:
                rig.calls.append("negative")
                return rig.negative()

        class _Report:
            def execute(self, request: ReportRequest) -> ReportOutcome:
                rig.calls.append("report")
                return _outcome(exceeds=rig.exceeds_report)

        return RunPipeline(
            profiles=profiles,
            preflight=_Pre(),
            probe=_Probe(),
            scan=_Scan(),
            report=_Report(),
            sink=self.sink,
            kill_switch=self.kill,
            clock=self.clock,
            run_id_fallback="fallback-run",
            authz=_Authz(),
            negative=_Negative(),
            nuclei=_Nuclei() if self.wire_nuclei else None,
        ).execute(request)


def _status(result: RunResult) -> dict[str, str]:
    return {stage.name: stage.status for stage in result.summary.stages}


def _message(result: RunResult, name: str) -> str:
    return next(stage.message or "" for stage in result.summary.stages if stage.name == name)


_ALL = ["preflight", "probe", "scan", "nuclei", "authz", "negative", "report"]


def test_nuclei_roda_depois_do_scan_e_antes_do_authz_quando_o_perfil_tem_a_chave() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo"))

    assert rig.calls == _ALL
    assert result.error is None
    assert _status(result)["nuclei"] == "ok"
    assert [stage.name for stage in result.summary.stages] == _ALL
    assert result.summary.options.nuclei is True


def test_a_etapa_recebe_a_pasta_o_prazo_unico_e_nenhum_modelo_fixo() -> None:
    rig = Rig()

    rig.run(RunRequest(product="demo", max_minutes=20))

    (request,) = rig.nuclei_requests
    assert request.run_id == RUN_ID
    assert request.deadline is not None
    assert request.only_templates == ()


def test_no_nuclei_pula_a_etapa_e_diz_o_motivo() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", nuclei=False))

    assert "nuclei" not in rig.calls
    assert _status(result)["nuclei"] == "skipped"
    assert "--no-nuclei" in _message(result, "nuclei")
    assert result.summary.options.nuclei is False
    assert result.summary.nuclei_findings_by_severity is None
    assert rig.calls[-3:] == ["authz", "negative", "report"]


def test_only_pula_a_etapa_porque_o_nuclei_nao_filtra_por_operacao() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", only=("ver",)))

    assert "nuclei" not in rig.calls
    assert _status(result)["nuclei"] == "skipped"
    assert "--only" in _message(result, "nuclei")


def test_perfil_sem_a_chave_pula_a_etapa_e_nao_monta_nada() -> None:
    rig = Rig(profile_nuclei=False)

    result = rig.run(RunRequest(product="demo"))

    assert "nuclei" not in rig.calls
    assert _status(result)["nuclei"] == "skipped"
    assert "extra_checks.nuclei" in _message(result, "nuclei")


def test_nuclei_ligado_na_linha_de_comando_nao_liga_perfil_sem_a_chave() -> None:
    rig = Rig(profile_nuclei=False)

    result = rig.run(RunRequest(product="demo", nuclei=True))

    assert "nuclei" not in rig.calls
    assert _status(result)["nuclei"] == "skipped"
    assert result.summary.nuclei_findings_by_severity is None


def test_skip_scan_pula_o_nuclei_e_aponta_o_comando_solto() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", skip_scan=True))

    assert rig.calls == ["preflight", "probe"]
    assert _status(result)["nuclei"] == "skipped"
    assert "hdast nuclei PRODUTO --run RUN_ID" in _message(result, "nuclei")


def test_skip_scan_com_no_nuclei_mantem_a_mensagem_curta() -> None:
    result = Rig().run(RunRequest(product="demo", skip_scan=True, nuclei=False))

    assert _message(result, "nuclei") == "Pedido com --skip-scan e --no-nuclei."


def test_resumo_traz_achados_por_severidade_e_modelos_rodados_e_excluidos() -> None:
    rig = Rig(
        nuclei=lambda: nuclei_result(
            findings=(nuclei_finding(severity="high"), nuclei_finding("b-id", severity="low")),
            selected=7,
            excluded=(("unsafe", 3), ("writes_not_allowed", 2)),
        )
    )

    result = rig.run(RunRequest(product="demo"))

    assert result.summary.nuclei_findings_by_severity == {
        "high": 1,
        "medium": 0,
        "low": 1,
        "informational": 0,
    }
    assert result.summary.nuclei_templates_selected == 7
    assert result.summary.nuclei_templates_excluded == {"unsafe": 3, "writes_not_allowed": 2}
    assert rig.sink.summaries[RUN_ID] is result.summary


def test_achado_do_nuclei_no_limiar_do_perfil_faz_o_run_sair_com_1() -> None:
    rig = Rig(fail_on="medium", nuclei=lambda: nuclei_result(findings=(nuclei_finding(),)))

    result = rig.run(RunRequest(product="demo"))

    assert result.error is None
    assert result.summary.exit_code == int(ExitCode.FINDINGS)
    assert result.summary.status == "findings"


def test_achado_do_nuclei_abaixo_do_limiar_nao_muda_o_codigo() -> None:
    rig = Rig(fail_on="high", nuclei=lambda: nuclei_result(findings=(nuclei_finding(),)))

    result = rig.run(RunRequest(product="demo"))

    assert result.summary.exit_code == 0
    assert result.summary.status == "completed"


def test_fail_on_da_linha_de_comando_endurece_o_gate_do_nuclei() -> None:
    rig = Rig(nuclei=lambda: nuclei_result(findings=(nuclei_finding(severity="low"),)))

    result = rig.run(RunRequest(product="demo", fail_on="low"))

    assert result.summary.exit_code == int(ExitCode.FINDINGS)


def test_sem_achados_do_nuclei_o_gate_segue_o_do_report() -> None:
    rig = Rig(fail_on="low", exceeds_report=True)

    result = rig.run(RunRequest(product="demo"))

    assert result.summary.exit_code == int(ExitCode.FINDINGS)


def test_nuclei_parado_pelo_prazo_ainda_gera_o_report_e_guarda_o_codigo_dele() -> None:
    rig = Rig(nuclei=lambda: nuclei_result("stopped_deadline", message="Prazo."))

    result = rig.run(RunRequest(product="demo"))

    assert rig.calls == ["preflight", "probe", "scan", "nuclei", "report"]
    assert result.summary.exit_code == int(ExitCode.SCOPE)
    assert _status(result)["nuclei"] == "failed"
    assert _status(result)["authz"] == "not_run"
    assert _status(result)["report"] == "ok"
    assert result.summary.nuclei_findings_by_severity is not None


def test_falha_da_ferramenta_e_registrada_no_padrao_dos_estagios() -> None:
    error = ExternalToolError("O Nuclei terminou com erro.", hint="Rode de novo.")
    rig = Rig(nuclei_error=error)

    result = rig.run(RunRequest(product="demo"))

    nuclei = next(stage for stage in result.summary.stages if stage.name == "nuclei")
    assert nuclei.status == "failed"
    assert nuclei.exit_code == int(ExitCode.EXTERNAL_TOOL)
    assert nuclei.error_code == "EXTERNAL_TOOL_ERROR"
    assert nuclei.message == "O Nuclei terminou com erro."
    assert result.summary.exit_code == int(ExitCode.EXTERNAL_TOOL)
    assert result.summary.nuclei_findings_by_severity is None
    assert rig.calls[-1] == "report"


def test_perfil_com_a_chave_e_etapa_nao_montada_e_erro_de_configuracao() -> None:
    rig = Rig(wire_nuclei=False)

    result = rig.run(RunRequest(product="demo"))

    assert result.summary.exit_code == int(ExitCode.USAGE)
    assert _status(result)["nuclei"] == "failed"


def test_o_nuclei_parado_pela_trava_vira_interrupcao_130() -> None:
    rig = Rig(nuclei=lambda: nuclei_result("stopped_kill", message="Contêiner derrubado."))
    original = rig.nuclei

    def engage() -> NucleiResult:
        rig.kill.on = True
        return original()

    rig.nuclei = engage

    result = rig.run(RunRequest(product="demo"))

    assert result.summary.exit_code == int(ExitCode.INTERRUPTED)
    assert result.summary.stop_requested is True
    assert "authz" not in rig.calls


def test_scan_que_falha_nunca_chega_ao_nuclei() -> None:
    rig = Rig(scan=lambda: _scan("stopped_zap", "ZAP caiu"))

    result = rig.run(RunRequest(product="demo"))

    assert "nuclei" not in rig.calls
    assert _status(result)["nuclei"] == "not_run"


def test_modelos_do_reteste_chegam_ao_estagio() -> None:
    rig = Rig()

    rig.run(RunRequest(product="demo", nuclei_templates=("http/misconfiguration/a.yaml",)))

    (request,) = rig.nuclei_requests
    assert request.only_templates == ("http/misconfiguration/a.yaml",)


def test_erro_de_configuracao_do_nuclei_nao_vira_excecao_solta() -> None:
    rig = Rig(nuclei_error=ConfigError("Sem pilha.", hint="Suba a pilha."))

    result = rig.run(RunRequest(product="demo"))

    assert result.summary.exit_code == int(ExitCode.USAGE)


def test_only_com_modelos_do_reteste_nao_pula_o_nuclei() -> None:
    rig = Rig()
    templates = ("http/misconfiguration/a.yaml",)

    result = rig.run(RunRequest(product="demo", only=("ver",), nuclei_templates=templates))

    assert "nuclei" in rig.calls
    assert _status(result)["nuclei"] == "ok"
    (request,) = rig.nuclei_requests
    assert request.only_templates == templates


def test_nuclei_only_roda_so_o_preflight_e_o_nuclei_sobre_a_pasta_do_preflight() -> None:
    rig = Rig()
    templates = ("http/misconfiguration/a.yaml",)

    result = rig.run(RunRequest(product="demo", nuclei_only=True, nuclei_templates=templates))

    assert rig.calls == ["preflight", "nuclei"]
    assert _status(result) == {
        "preflight": "ok",
        "probe": "skipped",
        "scan": "skipped",
        "nuclei": "ok",
        "authz": "skipped",
        "negative": "skipped",
        "report": "skipped",
    }
    assert result.summary.options.nuclei_only is True
    (request,) = rig.nuclei_requests
    assert request.only_templates == templates
    assert request.deadline is not None


def test_nuclei_only_com_achado_alto_sai_com_1_pelo_gate_do_proprio_estagio() -> None:
    rig = Rig(
        fail_on="high", nuclei=lambda: nuclei_result(findings=(nuclei_finding(severity="high"),))
    )

    result = rig.run(RunRequest(product="demo", nuclei_only=True, nuclei_templates=("x.yaml",)))

    assert result.error is None
    assert result.summary.exit_code == int(ExitCode.FINDINGS)


def test_nuclei_only_com_o_perfil_sem_a_chave_pula_o_estagio() -> None:
    rig = Rig(profile_nuclei=False)

    result = rig.run(RunRequest(product="demo", nuclei_only=True, nuclei_templates=("x.yaml",)))

    assert rig.calls == ["preflight"]
    assert _status(result)["nuclei"] == "skipped"


def test_nuclei_only_com_falha_do_estagio_para_com_o_codigo_dele() -> None:
    rig = Rig(nuclei_error=ConfigError("Sem pilha.", hint="Suba a pilha."))

    result = rig.run(RunRequest(product="demo", nuclei_only=True, nuclei_templates=("x.yaml",)))

    assert result.summary.exit_code == int(ExitCode.USAGE)
    assert _status(result)["nuclei"] == "failed"
