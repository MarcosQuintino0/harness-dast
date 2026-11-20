"""Portas consumidas pela capacidade panel; assinaturas e docstrings preservadas."""

from collections.abc import Mapping
from typing import Protocol

from harness_dast.domain.agent_metrics import AgentMetrics
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.run_metrics import RunMetrics
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.scan_result import ScanResult


class PanelFiles(Protocol):
    """Arquivos da execução que o painel lê e as páginas que ele grava (ADR 0032).

    Todo arquivo de leitura é opcional: ausente ou ilegível devolve `None` (ilegível levanta
    `ConfigError`, e o caso de uso trata os dois do mesmo jeito: "não medido"). Também acha a
    execução mais recente de um produto e grava as páginas HTML em `runs/<run_id>/panel/`.
    Nenhuma página grava fora dessa pasta.
    """

    def read_manifest(self, run_id: str) -> RunManifest | None:
        """Lê `manifest.json`; `None` se não existe."""
        ...

    def read_probe(self, run_id: str) -> ProbeResult | None:
        """Lê `probe.json`; `None` se não existe."""
        ...

    def read_scan(self, run_id: str) -> ScanResult | None:
        """Lê `scan.json`; `None` se não existe."""
        ...

    def read_findings(self, run_id: str) -> FindingsReport | None:
        """Lê `findings.json`; `None` se não existe."""
        ...

    def read_authz(self, run_id: str) -> AuthzResult | None:
        """Lê `authz.json`; `None` se o estágio não rodou."""
        ...

    def read_negative(self, run_id: str) -> NegativeResult | None:
        """Lê `negative.json`; `None` se o estágio não rodou."""
        ...

    def read_summary(self, run_id: str) -> RunSummary | None:
        """Lê `run.json`; `None` quando a execução não passou pelo `hdast run`.

        Raises:
            ConfigError: Arquivo ilegível ou inválido.
        """
        ...

    def read_metrics(self, run_id: str) -> RunMetrics | None:
        """Lê `metrics.json`; `None` quando não existe (execução anterior à medição).

        Raises:
            ConfigError: Arquivo ilegível ou inválido.
        """
        ...

    def read_agent_metrics(self, run_id: str) -> AgentMetrics | None:
        """Lê `agent-metrics.json` (tokens do agente, gravado pela avaliação cega).

        Devolve `None` quando não existe ou não é usável (JSON inválido, versão de formato
        desconhecida): o painel mostra "não medido" e nunca derruba a geração.
        """
        ...

    def latest_run_id(self, product: str) -> str | None:
        """Execução mais recente do produto (pelo carimbo do `run_id`), ou `None`."""
        ...

    def write_pages(self, run_id: str, pages: Mapping[str, str]) -> tuple[str, ...]:
        """Grava as páginas (nome do arquivo -> HTML) e devolve os caminhos relativos à execução.

        Garante: cada arquivo é gravado de forma atômica e o nome nunca sai da pasta do painel.

        Raises:
            ConfigError: Nome de página inválido ou falha de escrita.
        """
        ...
