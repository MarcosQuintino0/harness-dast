"""Portas de `scan` e `report`: a API de varredura do ZAP, os arquivos da execução e os destinos.

Ficam aqui, e não em `ports.py`, porque `ports.py` é um arquivo compartilhado que outros casos
de uso editam ao mesmo tempo; a regra é a mesma (porta declarada por quem a consome, sem regra
de negócio). Os adaptadores são `adapters/zap/scan_client.py` e `adapters/reporting/`.
"""

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.redaction import EvidenceMessage
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.rule_stats import RuleStat, RuleStatsFile
from harness_dast.domain.run_metrics import RunMetrics
from harness_dast.domain.run_summary import RunSummary, StageRecord
from harness_dast.domain.scan_policy import ScanLimits, ScanPolicy
from harness_dast.domain.scan_result import ScanProgress, ScanResult, ScanStatus
from harness_dast.domain.scan_tokens import ReplacerRule
from harness_dast.domain.traffic import ProxyRow
from harness_dast.domain.zap_messages import ZapMessage


class ScanStart(BaseModel):
    """Pedido de uma varredura de UMA requisição aprendida.

    Attributes:
        url: URL aprendida (em memória; nunca gravada).
        method: Método da requisição aprendida.
        body: Corpo aprendido, idêntico ao do ZAP (exigido para achar o nó), ou `None`.
        context_id: Contexto do ZAP da execução. SEMPRE enviado: sem ele o ZAP varre qualquer URL.
        policy_name: Política de varredura.
        max_scan_minutes: Teto desta varredura.
    """

    model_config = ConfigDict(frozen=True)

    url: str = Field(repr=False)
    method: str
    body: str | None = Field(default=None, repr=False)
    context_id: int
    policy_name: str
    max_scan_minutes: int


class ScanControl(Protocol):
    """API de varredura, regras do Replacer, alertas e mensagens do ZAP."""

    def verify_context(self, name: str, context_id: int) -> None:
        """Confere que o contexto do `probe` ainda existe com o mesmo id.

        Raises:
            ExternalToolError: Falha da API, ou contexto ausente (sessão do ZAP trocada).
        """
        ...

    def list_messages(self, base_url: str) -> tuple[ZapMessage, ...]:
        """Mensagens do histórico cujo URL começa por `base_url` (todas as páginas).

        Raises:
            ExternalToolError: Falha da API do ZAP.
        """
        ...

    def get_message(self, message_id: int) -> ZapMessage:
        """Uma mensagem do histórico (requisição e resposta).

        Raises:
            ExternalToolError: Falha da API, ou mensagem inexistente ou grande demais.
        """
        ...

    def apply_policy(self, policy: ScanPolicy, limits: ScanLimits) -> None:
        """Fixa limites, injeção em caminho e política ANTES da primeira varredura.

        Garante: threads por host, atraso, teto de duração e de regra, máscara de injeção e a
        política (recriada, com as regras desligadas) ficam definidos explicitamente.

        Raises:
            ExternalToolError: Falha da API, ou uma regra que devia estar desligada continua
                ligada depois de aplicada a política.
        """
        ...

    def start_scan(self, request: ScanStart) -> str:
        """Inicia a varredura (sem recursão, sem spider) e devolve o id.

        Raises:
            ExternalToolError: Falha da API, ou o ZAP recusou a URL (fora do contexto).
        """
        ...

    def scan_status(self, scan_id: str) -> ScanStatus:
        """Estado e progresso de uma varredura.

        Raises:
            ExternalToolError: Falha da API, ou varredura desconhecida.
        """
        ...

    def scan_rules(self, scan_id: str) -> tuple[RuleStat, ...]:
        """Tempo, pedidos e alertas de cada regra de uma varredura (só medição, ADR 0031).

        Raises:
            ExternalToolError: Falha da API, varredura desconhecida ou resposta fora da forma
                conhecida.
        """
        ...

    def stop_scan(self, scan_id: str) -> None:
        """Para uma varredura (`ascan/action/stop`).

        Raises:
            ExternalToolError: Falha da API.
        """
        ...

    def list_alerts(self, base_url: str) -> tuple[dict[str, str], ...]:
        """Alertas da sessão para o `base_url`, como o ZAP devolve (todas as páginas).

        Raises:
            ExternalToolError: Falha da API ou alerta com formato inesperado.
        """
        ...

    def add_replacer_rule(self, rule: ReplacerRule) -> None:
        """Instala uma regra do Replacer.

        Raises:
            ExternalToolError: Falha da API ou add-on ausente.
        """
        ...

    def remove_replacer_rule(self, description: str) -> None:
        """Remove uma regra do Replacer pelo nome.

        Raises:
            ExternalToolError: Falha da API.
        """
        ...

    def remove_scan_policy(self, name: str) -> None:
        """Remove a política de varredura, se existir (não é erro se não existe).

        Raises:
            ExternalToolError: Falha da API.
        """
        ...


class RunArtifacts(Protocol):
    """Arquivos de uma execução que `scan` e `report` leem e gravam.

    Tudo o que se grava aqui já foi redigido; este armazém não redige.
    """

    def read_manifest(self, run_id: str) -> RunManifest:
        """Lê `manifest.json`.

        Raises:
            ConfigError: Execução ou arquivo ausente, ilegível ou inválido.
        """
        ...

    def read_probe(self, run_id: str) -> ProbeResult:
        """Lê `probe.json`.

        Raises:
            ConfigError: Arquivo ausente, ilegível ou inválido.
        """
        ...

    def read_audit(self, run_id: str) -> tuple[AuditEntry, ...]:
        """Lê `audit.jsonl` (linha ilegível é erro).

        Raises:
            ConfigError: Arquivo ausente, ilegível ou inválido.
        """
        ...

    def write_scan(self, run_id: str, result: ScanResult) -> None:
        """Grava `scan.json` de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def write_progress(self, run_id: str, progress: ScanProgress) -> None:
        """Grava `scan-progress.json` de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def write_alerts(self, run_id: str, alerts: Sequence[dict[str, str]]) -> None:
        """Grava `alerts.raw.json` (alertas já redigidos) de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def write_evidence(self, run_id: str, messages: Sequence[EvidenceMessage]) -> None:
        """Grava `evidence.json` (mensagens já redigidas) de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def read_scan(self, run_id: str) -> ScanResult:
        """Lê `scan.json`.

        Raises:
            ConfigError: Arquivo ausente (o `scan` não rodou), ilegível ou inválido.
        """
        ...

    def read_alerts(self, run_id: str) -> tuple[dict[str, object], ...]:
        """Lê `alerts.raw.json`.

        Raises:
            ConfigError: Arquivo ausente, ilegível ou com formato inválido.
        """
        ...

    def read_evidence(self, run_id: str) -> tuple[EvidenceMessage, ...]:
        """Lê `evidence.json`; vazio quando o arquivo não existe.

        Raises:
            ConfigError: Arquivo ilegível ou inválido.
        """
        ...

    def read_triage(self, run_id: str) -> object | None:
        """Lê `triage.json` como JSON bruto; `None` quando não existe.

        Raises:
            ConfigError: Arquivo ilegível ou que não é JSON.
        """
        ...

    def read_findings(self, run_id: str) -> FindingsReport:
        """Lê `findings.json` de outra execução (para `--compare`).

        Raises:
            ConfigError: Execução ou arquivo ausente, ilegível ou inválido.
        """
        ...

    def read_authz(self, run_id: str) -> AuthzResult | None:
        """Lê `authz.json`; `None` quando o estágio de autorização não rodou (ADR 0027).

        Raises:
            ConfigError: Arquivo ilegível ou inválido.
        """
        ...

    def write_rule_stats(self, run_id: str, stats: RuleStatsFile) -> None:
        """Grava `rule-stats.json` (medição por regra do ZAP, ADR 0031) de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...

    def read_rule_stats(self, run_id: str) -> RuleStatsFile | None:
        """Lê `rule-stats.json`; `None` quando o `scan` não o gravou.

        Raises:
            ConfigError: Arquivo ilegível ou inválido.
        """
        ...

    def write_metrics(self, run_id: str, metrics: RunMetrics) -> None:
        """Grava `metrics.json` (ADR 0031) de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...


class RunningScans(Protocol):
    """Varreduras em andamento, lidas dos `scan-progress.json` (para `hdast stop`)."""

    def running(self) -> tuple[ScanProgress, ...]:
        """Andamentos com `status` `running`, de qualquer execução; ilegíveis são ignorados."""
        ...


class ProxyAudit(Protocol):
    """Leitura da trilha de auditoria do proxy de escopo."""

    def rows(self) -> tuple[ProxyRow, ...]:
        """Linhas da trilha, em ordem; vazio se ainda não existe.

        Raises:
            ConfigError: Linha ilegível.
        """
        ...


class RunSummarySink(Protocol):
    """Grava o `run.json` e diz quais artefatos existem na pasta da execução."""

    def write_summary(self, run_id: str, summary: RunSummary) -> None:
        """Grava `run.json`.

        Raises:
            ConfigError: A pasta da execução não pôde ser escrita.
        """
        ...

    def existing_files(self, run_id: str) -> dict[str, str]:
        """Artefatos conhecidos que existem na pasta (nome -> nome do arquivo)."""
        ...


class ReportSink(Protocol):
    """Destino do relatório (JSON, Markdown e, no futuro, SARIF, DefectDojo, Jira)."""

    def write(self, run_id: str, report: FindingsReport) -> str:
        """Grava o relatório e devolve o nome do arquivo gerado.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...


class RunMetricsRecorder(Protocol):
    """Grava ou atualiza o `metrics.json` de uma execução (ADR 0031).

    Garante: nunca levanta erro do harness. A medição é secundária: se não puder ser montada
    ou gravada, o erro vai para o log estruturado e o comando que a chamou segue.
    """

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
            O nome do arquivo gravado, ou `None` se não foi possível gravar.
        """
        ...
