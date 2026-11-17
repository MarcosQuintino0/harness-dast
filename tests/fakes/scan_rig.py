"""Cenário completo de `scan` e `report` com falsos: o `probe` roda de verdade sobre o falso do
alvo, e o ZAP falso "aprende" as requisições dele."""

from typing import Any

from harness_dast.application.common_ports import KillSwitch
from harness_dast.application.metrics import MetricsRecorder
from harness_dast.application.panel_index_ports import ScanLive
from harness_dast.application.probe import ProbeRequest
from harness_dast.application.report import Report
from harness_dast.application.scan import Scan, ScanRequest
from harness_dast.application.scan_ports import OastEvents, ProcessSampler
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.scan_result import ScanResult
from tests.fakes.rig import Rig
from tests.fakes.scan_ports import FakeProxyAudit, FakeScanZap, InMemoryRunArtifacts


class ListSink:
    """`ReportSink` falso: guarda o que recebeu e devolve um nome de arquivo."""

    def __init__(self, name: str = "list.json") -> None:
        self.name = name
        self.reports: list[tuple[str, FindingsReport]] = []

    def write(self, run_id: str, report: FindingsReport) -> str:
        self.reports.append((run_id, report))
        return self.name


class ScanRig(Rig):
    """`Rig` do `probe` mais o ZAP de varredura e o armazém de artefatos."""

    zap: FakeScanZap

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.zap = FakeScanZap()
        self.scanner = self.zap
        self.artifacts = InMemoryRunArtifacts(self.store)
        self.sink = ListSink()
        self._probe_result: ProbeResult | None = None

    def run_probe(self, **changes: Any) -> ProbeResult:
        """Roda o `probe` (real, sobre o alvo falso) e deixa o ZAP falso conhecer o resultado."""
        result = self.probe().execute(ProbeRequest(product="agenda", **changes))
        self.zap.context = (self.zap.contexts[-1][0], len(self.zap.contexts))
        self.zap.learn_from(self.target, self.store, result.run_id)
        self._probe_result = result
        return result

    @property
    def probe_result(self) -> ProbeResult:
        """Resultado do `probe` já executado."""
        assert self._probe_result is not None
        return self._probe_result

    def scan(
        self,
        live: ScanLive | None = None,
        process_sampler: ProcessSampler | None = None,
        kill_switch: KillSwitch | None = None,
        oast: OastEvents | None = None,
    ) -> Scan:
        return Scan(
            profiles=self.profiles,
            specs=self._specs(),
            documents=self.documents,
            secrets=self.secrets,
            vault=self.vault,
            client=self.target,
            zap=self.zap,
            scanner=self.scanner,
            store=self.store,
            artifacts=self.artifacts,
            clock=self.clock,
            sleeper=self.clock,
            live=live,
            process_sampler=process_sampler,
            kill_switch=kill_switch,
            oast=oast,
            exchanges=self.artifacts,
            entropy=self.entropy,
        )

    def metrics_recorder(self, audit: FakeProxyAudit | None = None) -> MetricsRecorder:
        return MetricsRecorder(
            profiles=self.profiles,
            artifacts=self.artifacts,
            proxy_audit=audit,
            clock=self.clock,
            harness_version="0.0-test",
        )

    def report(
        self, *, with_metrics: bool = False, proxy_audit: FakeProxyAudit | None = None
    ) -> Report:
        return Report(
            profiles=self.profiles,
            artifacts=self.artifacts,
            sinks=[self.sink],
            clock=self.clock,
            harness_version="0.0-test",
            metrics=self.metrics_recorder() if with_metrics else None,
            proxy_audit=proxy_audit,
        )

    def run_scan(self, **changes: Any) -> ScanResult:
        """Atalho: roda o `scan` sobre o `probe` mais recente."""
        request = ScanRequest(product="agenda", run_id=self.probe_result.run_id, **changes)
        return self.scan().execute(request)

    def _specs(self) -> Any:
        from tests.fakes.probe_ports import InMemorySpecs

        return InMemorySpecs(self.spec)
