"""Gravação do `metrics.json` de uma execução (ADR 0031): onde o tempo foi.

Junta o que as etapas já gravaram na pasta da execução e as linhas da auditoria do proxy, monta
a medição no domínio (`build_run_metrics`) e a grava. É chamado pelo `report` e pelo `run`; cada
chamada refaz o arquivo inteiro a partir do que existe, então chamar duas vezes é seguro.

A medição é secundária: NUNCA derruba o comando que a pediu. Qualquer `HarnessError` ao ler ou
gravar vira registro no log estruturado e a chamada devolve `None`. Nenhum dado do alvo e nenhum
segredo passa por aqui: só números e identificadores.
"""

from collections.abc import Callable, Sequence

import structlog

from harness_dast.application.ports import Clock, ProfileRepository
from harness_dast.application.scan_ports import ProxyAudit, RunArtifacts
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.run_metrics import build_run_metrics
from harness_dast.domain.run_summary import StageRecord
from harness_dast.domain.traffic import ProxyRow

METRICS_FILE = "metrics.json"

_log = structlog.get_logger()


class MetricsRecorder:
    """Monta e grava o `metrics.json` (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        artifacts: RunArtifacts,
        proxy_audit: ProxyAudit | None,
        clock: Clock,
        harness_version: str,
    ) -> None:
        """Cria o gravador com as portas de que precisa.

        Args:
            profiles: Repositório de perfis (dá o modo de caminho).
            artifacts: Arquivos da execução.
            proxy_audit: Auditoria do proxy, ou `None` sem pilha gerenciada (sem lacunas).
            clock: Relógio injetado.
            harness_version: Versão do `hdast`.
        """
        self._profiles = profiles
        self._artifacts = artifacts
        self._audit = proxy_audit
        self._clock = clock
        self._version = harness_version

    def refresh(
        self,
        product: str,
        run_id: str,
        *,
        report_seconds: float | None = None,
        stages: Sequence[StageRecord] | None = None,
        run_window: tuple[str, str] | None = None,
    ) -> str | None:
        """Monta `metrics.json` com o que a execução já tem e o grava.

        Returns:
            O nome do arquivo gravado, ou `None` se a medição não pôde ser feita.
        """
        try:
            metrics = build_run_metrics(
                manifest=self._artifacts.read_manifest(run_id),
                probe=self._optional(run_id, "probe.json", self._artifacts.read_probe),
                scan=self._optional(run_id, "scan.json", self._artifacts.read_scan),
                authz=self._optional(run_id, "authz.json", self._artifacts.read_authz),
                rule_stats=self._optional(
                    run_id, "rule-stats.json", self._artifacts.read_rule_stats
                ),
                proxy_rows=self._rows(run_id),
                stages=stages,
                run_window=run_window,
                report_seconds=report_seconds,
                path_mode=self._profiles.load(product).scope.path_mode,
                harness_version=self._version,
                generated_at=self._clock.now().isoformat(),
            )
            self._artifacts.write_metrics(run_id, metrics)
        except HarnessError as error:
            _log.warning("metrics_not_written", run_id=run_id, reason=error.message)
            return None
        return METRICS_FILE

    def _optional[T](self, run_id: str, name: str, read: Callable[[str], T]) -> T | None:
        """Lê um arquivo opcional; ausente ou ilegível vira `None` e fica no log."""
        try:
            return read(run_id)
        except HarnessError as error:
            _log.info("metrics_input_unavailable", run_id=run_id, file=name, reason=error.message)
            return None

    def _rows(self, run_id: str) -> tuple[ProxyRow, ...] | None:
        if self._audit is None:
            return None
        try:
            return self._audit.rows()
        except HarnessError as error:
            _log.warning("metrics_audit_unavailable", run_id=run_id, reason=error.message)
            return None
