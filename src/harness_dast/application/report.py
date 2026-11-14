"""Caso de uso `report`: transforma os alertas brutos da execução em achados e relatórios.

Não toca rede nem ZAP: lê só arquivos da execução (`probe.json`, `scan.json`,
`alerts.raw.json`, `evidence.json` e, se existir, `triage.json`), monta o `FindingsReport` no
domínio e entrega aos destinos (`ReportSink`: JSON e Markdown). Não confere janela nem
autorização: ler arquivos não envia nada ao alvo.

Dono do código de saída 1: é o `report` (o `scan` só coleta). Com um limiar de severidade
(`--fail-on` ou `scan.fail_on` do perfil), `exceeds_threshold` diz se há achado igual ou acima
dele, contando TODOS os achados: a triagem do agente não retira nada da conta. `--fail-on` só
endurece o limiar do perfil (`effective_fail_on`); severidade desconhecida conta como acima.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from harness_dast.application.ports import Clock, ProfileRepository
from harness_dast.application.scan_ports import ReportSink, RunArtifacts, RunMetricsRecorder
from harness_dast.domain.auth import PasswordLoginAuth
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.report_build import assemble_report
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.scan_config import FailOn, effective_fail_on
from harness_dast.domain.triage import TriageFile, parse_triage
from harness_dast.domain.zap_alert import SEVERITY_RANK


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
    """

    report: FindingsReport
    files: tuple[str, ...]
    threshold: FailOn
    exceeds_threshold: bool
    metrics_file: str | None = None


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
    ) -> None:
        """Cria o caso de uso com as portas de que precisa.

        `metrics` grava o `metrics.json` depois dos relatórios; sem ele não há medição.
        """
        self._profiles = profiles
        self._artifacts = artifacts
        self._sinks = tuple(sinks)
        self._clock = clock
        self._version = harness_version
        self._metrics = metrics

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
        )
        files = tuple(sink.write(run_id, report) for sink in self._sinks)
        threshold = effective_fail_on(profile.scan.fail_on, request.fail_on)
        metrics_file = self._record_metrics(request, run_id, began)
        return ReportOutcome(report, files, threshold, exceeds(report, threshold), metrics_file)

    def _record_metrics(self, request: ReportRequest, run_id: str, began: datetime) -> str | None:
        if self._metrics is None:
            return None
        seconds = round((self._clock.now() - began).total_seconds(), 3)
        return self._metrics.refresh(request.product, run_id, report_seconds=seconds)

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

    Conta os achados do ZAP e os de autorização entre contas (`report.authz`).

    Severidade que a CLI não soube classificar (`unknown`: `Critical`, um ZAP em outro idioma,
    vazio) conta como acima de qualquer limiar diferente de `none`: o gate falha fechado.
    """
    if threshold == "none":
        return False
    floor = SEVERITY_RANK[threshold]
    severities = [item.proposed_severity for item in report.findings]
    if report.authz is not None:
        severities += [item.proposed_severity for item in report.authz.findings]
    return any(severity == "unknown" or SEVERITY_RANK[severity] >= floor for severity in severities)


def _placeholders(profile: ProductProfile) -> tuple[tuple[str, str] | None, str | None]:
    auth = profile.auth
    if isinstance(auth, PasswordLoginAuth):
        scheme = f"{auth.token_scheme} " if auth.token_scheme else ""
        header = (auth.token_header, f"{scheme}$TOKEN")
    else:
        header = (auth.header_name, "$API_KEY")
    return header, profile.auth.csrf.header_name if profile.auth.csrf else None
