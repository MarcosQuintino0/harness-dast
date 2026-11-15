"""Falsos do painel da execução: arquivos da execução em memória e o leitor do OpenAPI."""

from collections.abc import Mapping

from harness_dast.domain.agent_metrics import AgentMetrics
from harness_dast.domain.api_model import ApiSpec, Operation
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.run_metrics import RunMetrics
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.scan_result import ScanResult


class FakePanelFiles:
    """`PanelFiles` em memória: o que existe é o que o teste guardou; o resto é `None`."""

    def __init__(self) -> None:
        self.summary: dict[str, RunSummary] = {}
        self.manifest: dict[str, RunManifest] = {}
        self.probe: dict[str, ProbeResult] = {}
        self.scan: dict[str, ScanResult] = {}
        self.findings: dict[str, FindingsReport] = {}
        self.authz: dict[str, AuthzResult] = {}
        self.negative: dict[str, NegativeResult] = {}
        self.metrics: dict[str, RunMetrics] = {}
        self.agent_metrics: dict[str, AgentMetrics] = {}
        self.runs: list[str] = []
        self.written: dict[str, dict[str, str]] = {}
        self.unreadable: set[str] = set()
        self.write_error: ConfigError | None = None

    def _read[T](self, store: Mapping[str, T], name: str, run_id: str) -> T | None:
        if name in self.unreadable:
            raise ConfigError(f"O arquivo {name} da execução está ilegível.")
        return store.get(run_id)

    def read_summary(self, run_id: str) -> RunSummary | None:
        return self._read(self.summary, "run.json", run_id)

    def read_manifest(self, run_id: str) -> RunManifest | None:
        return self._read(self.manifest, "manifest.json", run_id)

    def read_probe(self, run_id: str) -> ProbeResult | None:
        return self._read(self.probe, "probe.json", run_id)

    def read_scan(self, run_id: str) -> ScanResult | None:
        return self._read(self.scan, "scan.json", run_id)

    def read_findings(self, run_id: str) -> FindingsReport | None:
        return self._read(self.findings, "findings.json", run_id)

    def read_authz(self, run_id: str) -> AuthzResult | None:
        return self._read(self.authz, "authz.json", run_id)

    def read_negative(self, run_id: str) -> NegativeResult | None:
        return self._read(self.negative, "negative.json", run_id)

    def read_metrics(self, run_id: str) -> RunMetrics | None:
        return self._read(self.metrics, "metrics.json", run_id)

    def read_agent_metrics(self, run_id: str) -> AgentMetrics | None:
        return self.agent_metrics.get(run_id)

    def latest_run_id(self, product: str) -> str | None:
        mine = [run for run in self.runs if f"-{product}-" in run]
        return max(mine) if mine else None

    def write_pages(self, run_id: str, pages: Mapping[str, str]) -> tuple[str, ...]:
        if self.write_error is not None:
            raise self.write_error
        self.written[run_id] = dict(pages)
        return tuple(f"panel/{name}" for name in pages)


class FakeSpecLoader:
    """`SpecLoader` que devolve as operações dadas, ou falha como um OpenAPI inválido."""

    def __init__(self, operations: tuple[Operation, ...] = (), *, fails: bool = False) -> None:
        self._operations = operations
        self._fails = fails
        self.loaded = 0

    def load(self, product: str, profile: ProductProfile) -> ApiSpec:
        self.loaded += 1
        if self._fails:
            raise ConfigError("OpenAPI inválido.")
        return ApiSpec(title="t", version="1", operations=self._operations)
