"""Armazém de `findings.json` e `retest.json` em memória, com o comportamento da porta."""

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.retest import RetestReport


class InMemoryRetestArtifacts:
    """Guarda relatórios por execução; ler uma execução ausente falha como o real."""

    def __init__(
        self,
        reports: dict[str, FindingsReport] | None = None,
        nuclei: dict[str, NucleiResult] | None = None,
    ) -> None:
        self.reports = dict(reports or {})
        self.nuclei = dict(nuclei or {})
        self.written: dict[str, RetestReport] = {}

    def read_findings(self, run_id: str) -> FindingsReport:
        if run_id not in self.reports:
            raise ConfigError("A execução não tem findings.json.", hint="Rode o report antes.")
        return self.reports[run_id]

    def read_nuclei(self, run_id: str) -> NucleiResult | None:
        return self.nuclei.get(run_id)

    def write_retest(self, run_id: str, report: RetestReport) -> str:
        self.written[run_id] = report
        return "retest.json"
