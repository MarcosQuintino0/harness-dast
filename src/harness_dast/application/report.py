"""Caso de uso `report`: transforma os alertas brutos da execução em achados e relatórios.

Não toca rede nem ZAP: lê só arquivos da execução (`probe.json`, `scan.json`,
`alerts.raw.json`, `evidence.json` e, se existir, `triage.json`), monta o `FindingsReport` no
domínio e entrega aos destinos (`ReportSink`: JSON e Markdown). Não confere janela nem
autorização: ler arquivos não envia nada ao alvo.

Os sinais de erro interno vistos pela cerca (ADR 0049) vêm da auditoria do proxy (`ProxyAudit`,
opcional): o `report` grava `error-signals.json` quando há linhas liberadas na janela da execução e,
sem auditoria, reaproveita o arquivo que já existe. Ler a auditoria nunca derruba o relatório.

Dono do código de saída 1: é o `report` (o `scan` só coleta). Com um limiar de severidade
(`--fail-on` ou `scan.fail_on` do perfil), `exceeds_threshold` diz se há achado igual ou acima
dele, contando TODOS os achados: a triagem do agente não retira nada da conta. `--fail-on` só
endurece o limiar do perfil (`effective_fail_on`); severidade desconhecida conta como acima.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import structlog

from harness_dast.application.ports import Clock, ProfileRepository, SpecLoader
from harness_dast.application.scan_ports import (
    PanelRefresher,
    ProxyAudit,
    ReportSink,
    RunArtifacts,
    RunMetricsRecorder,
)
from harness_dast.domain.auth import PasswordLoginAuth
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding_build import AlertResolver
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.report_build import assemble_report, build_resolver
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.scan_config import FailOn, effective_fail_on
from harness_dast.domain.scan_result import ScanResult
from harness_dast.domain.scan_rule_coverage import rule_coverage_gaps
from harness_dast.domain.signal_findings import build_proxy_signals, signal_window
from harness_dast.domain.signal_operations import signal_resolver
from harness_dast.domain.signal_result import ProxySignals, disabled_signals
from harness_dast.domain.traffic import ProxyRow
from harness_dast.domain.triage import TriageFile, parse_triage
from harness_dast.domain.zap_alert import SEVERITY_RANK

_log = structlog.get_logger()


@dataclass(frozen=True)
class ReportRequest:
    """Pedido de um `report`.

    Attributes:
        product: Produto.
        run_id: Execução com `probe.json`, `scan.json` e alertas.
        compare: Outra execução (com `findings.json`) para marcar novo, persistente e gone.
        fail_on: Limiar pedido; só endurece `scan.fail_on` do perfil (nunca afrouxa);
            `None` usa o do perfil.
    """

    product: str
    run_id: str
    compare: str | None = None
    fail_on: FailOn | None = None


@dataclass(frozen=True)
class ReportOutcome:
    """Resultado de um `report`.

    Attributes:
        report: O relatório gerado.
        files: Arquivos gravados pelos destinos.
        threshold: Limiar aplicado (`none` = sem gate).
        exceeds_threshold: Se há achado com severidade proposta no limiar ou acima.
        metrics_file: Arquivo de medição (`metrics.json`, ADR 0031) gravado junto, ou `None`.
        panel_file: Página de entrada do painel (ADR 0032) gerada junto, ou `None`.
    """

    report: FindingsReport
    files: tuple[str, ...]
    threshold: FailOn
    exceeds_threshold: bool
    metrics_file: str | None = None
    panel_file: str | None = None


class Report:
    """Orquestra o `report` (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        artifacts: RunArtifacts,
        sinks: Sequence[ReportSink],
        clock: Clock,
        harness_version: str,
        metrics: RunMetricsRecorder | None = None,
        panel: PanelRefresher | None = None,
        proxy_audit: ProxyAudit | None = None,
        specs: SpecLoader | None = None,
    ) -> None:
        """Cria o caso de uso com as portas de que precisa.

        `metrics` grava o `metrics.json` depois dos relatórios; sem ele não há medição. `panel`
        gera o painel da execução por último (ADR 0032); sem ele não há painel. `proxy_audit` é a
        trilha da cerca (ADR 0049); sem ela o `report` só reaproveita um `error-signals.json`.
        """
        self._profiles = profiles
        self._artifacts = artifacts
        self._sinks = tuple(sinks)
        self._clock = clock
        self._version = harness_version
        self._metrics = metrics
        self._panel = panel
        self._proxy_audit = proxy_audit
        self._specs = specs

    def execute(self, request: ReportRequest) -> ReportOutcome:
        """Gera o relatório.

        Raises:
            ConfigError: Execução sem `scan.json`, arquivo ilegível, triagem inválida,
                comparação impossível (outro produto ou outra versão de fingerprint) ou
                falha de escrita.
        """
        began = self._clock.now()
        profile = self._profiles.load(request.product)
        run_id = require_run_id(request.run_id)
        probe = self._artifacts.read_probe(run_id)
        scan = self._artifacts.read_scan(run_id)
        if scan.rule_coverage_gaps is None:
            stats = self._artifacts.read_rule_stats(run_id)
            if stats is not None and stats.run_id == scan.run_id:
                scan = scan.model_copy(
                    update={
                        "rule_coverage_gaps": rule_coverage_gaps(scan.entries, stats.operations)
                    }
                )
        if probe.product != profile.product or scan.product != profile.product:
            raise ConfigError(
                "A execução informada é de outro produto.",
                hint="Use o run_id do probe e do scan deste produto.",
            )
        authz = self._artifacts.read_authz(run_id)
        if authz is not None and authz.product != profile.product:
            raise ConfigError(
                "O authz.json da execução é de outro produto.",
                hint="Use o run_id do probe, do scan e do authz deste produto.",
            )
        negative = self._artifacts.read_negative(run_id)
        if negative is not None and negative.product != profile.product:
            raise ConfigError(
                "O negative.json da execução é de outro produto.",
                hint="Use o run_id do probe, do scan e do negative deste produto.",
            )
        baseline = self._baseline(request.compare, run_id)
        auth_header, csrf_header = _placeholders(profile)
        report = assemble_report(
            probe=probe,
            scan=scan,
            raw_alerts=self._artifacts.read_alerts(run_id),
            evidence={m.message_id: m for m in self._artifacts.read_evidence(run_id)},
            triage=self._triage(run_id),
            baseline=baseline,
            generated_at=self._clock.now().isoformat(),
            harness_version=self._version,
            auth_header=auth_header,
            csrf_header=csrf_header,
            authz=authz,
            proxy_signals=self._proxy_signals(run_id, probe, scan, authz, negative, profile),
            negative=negative,
        )
        files = tuple(sink.write(run_id, report) for sink in self._sinks)
        threshold = effective_fail_on(profile.scan.fail_on, request.fail_on)
        metrics_file = self._record_metrics(request, run_id, began)
        panel_file = self._panel.refresh(request.product, run_id) if self._panel else None
        return ReportOutcome(
            report, files, threshold, exceeds(report, threshold), metrics_file, panel_file
        )

    def _record_metrics(self, request: ReportRequest, run_id: str, began: datetime) -> str | None:
        if self._metrics is None:
            return None
        seconds = round((self._clock.now() - began).total_seconds(), 3)
        return self._metrics.refresh(request.product, run_id, report_seconds=seconds)

    def _proxy_signals(
        self,
        run_id: str,
        probe: ProbeResult,
        scan: ScanResult,
        authz: AuthzResult | None,
        negative: NegativeResult | None,
        profile: ProductProfile,
    ) -> ProxySignals:
        window = signal_window(
            probe.started_at,
            (
                probe.finished_at,
                scan.finished_at,
                authz.finished_at if authz else None,
                negative.finished_at if negative else None,
            ),
        )
        rows = self._audit_rows()
        if rows is not None and window is not None:
            built = build_proxy_signals(
                rows,
                product=probe.product,
                window=window,
                resolver=self._signal_resolver(probe, scan, profile),
            )
            if built.responses_total > 0:
                self._artifacts.write_signals(run_id, built)
                return built
        try:
            kept = self._artifacts.read_signals(run_id)
        except ConfigError as error:
            _log.warning("error_signals_unreadable", run_id=run_id, reason=error.message)
            kept = None
        return kept if kept is not None else disabled_signals()

    def _signal_resolver(
        self, probe: ProbeResult, scan: ScanResult, profile: ProductProfile
    ) -> AlertResolver:
        resolver = build_resolver(probe, scan)
        if self._specs is None:
            return resolver
        try:
            spec = self._specs.load(probe.product, profile)
        except ConfigError as error:
            _log.warning("signals_spec_unavailable", reason=error.message)
            return resolver
        return signal_resolver(resolver, spec)

    def _audit_rows(self) -> tuple[ProxyRow, ...] | None:
        if self._proxy_audit is None:
            return None
        try:
            return self._proxy_audit.rows()
        except ConfigError as error:
            _log.warning("proxy_audit_unreadable", reason=error.message)
            return None

    def _baseline(self, other: str | None, run_id: str) -> FindingsReport | None:
        if other is None:
            return None
        other_id = require_run_id(other)
        if other_id == run_id:
            raise ConfigError(
                "--compare precisa de OUTRA execução.",
                hint="Informe o run_id de uma execução anterior.",
            )
        return self._artifacts.read_findings(other_id)

    def _triage(self, run_id: str) -> TriageFile | None:
        data = self._artifacts.read_triage(run_id)
        return None if data is None else parse_triage(data)


def exceeds(report: FindingsReport, threshold: FailOn) -> bool:
    """Diz se algum achado tem severidade proposta igual ou acima do limiar (`none` = nunca).

    Conta os achados do ZAP, os de autorização entre contas (`report.authz`) e os de sinal de erro
    interno vistos pela cerca (`report.proxy_signals`, ADR 0049) e os de valores que o esquema
    proíbe (`report.negative`, ADR 0051): achado de origem própria não contorna o gate.

    Severidade que a CLI não soube classificar (`unknown`: `Critical`, um ZAP em outro idioma,
    vazio) conta como acima de qualquer limiar diferente de `none`: o gate falha fechado.
    """
    if threshold == "none":
        return False
    floor = SEVERITY_RANK[threshold]
    severities = [item.proposed_severity for item in report.findings]
    if report.authz is not None:
        severities += [item.proposed_severity for item in report.authz.findings]
    if report.negative is not None:
        severities += [item.proposed_severity for item in report.negative.findings]
    if report.proxy_signals is not None:
        severities += [item.proposed_severity for item in report.proxy_signals.findings]
    return any(severity == "unknown" or SEVERITY_RANK[severity] >= floor for severity in severities)


def _placeholders(profile: ProductProfile) -> tuple[tuple[str, str] | None, str | None]:
    auth = profile.auth
    if isinstance(auth, PasswordLoginAuth):
        scheme = f"{auth.token_scheme} " if auth.token_scheme else ""
        header = (auth.token_header, f"{scheme}$TOKEN")
    else:
        header = (auth.header_name, "$API_KEY")
    return header, profile.auth.csrf.header_name if profile.auth.csrf else None
