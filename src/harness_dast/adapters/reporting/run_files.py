"""Armazém dos arquivos de `scan` e `report` em `<runs_dir>/<run_id>/` (implementa `RunArtifacts`).

Leitura: limite de tamanho, JSON estrito e modelos validados; qualquer problema vira
`ConfigError` com a dica de qual comando refazer, sem repetir o conteúdo do arquivo. Escrita:
arquivo temporário e `os.replace`, para nunca existir um arquivo pela metade. Este armazém NÃO
redige: quem grava já entregou texto redigido (`domain.redaction`).

Arquivos: `scan.json`, `scan-progress.json`, `alerts.raw.json`, `evidence.json`, `authz.json`,
`rule-stats.json` e `metrics.json` (escritos aqui); `manifest.json`, `probe.json`,
`exchanges.json`, `audit.jsonl`, `triage.json` e `findings.json` (lidos).
"""

import json
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final, TypeVar

from pydantic import BaseModel, ValidationError

from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.redaction import EvidenceMessage
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.rule_stats import RuleStatsFile
from harness_dast.domain.run_metrics import RunMetrics
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.scan_result import ScanProgress, ScanResult

SCAN_FILE: Final = "scan.json"
PROGRESS_FILE: Final = "scan-progress.json"
REPLACE_ATTEMPTS: Final = 6
REPLACE_PAUSE_SECONDS: Final = 0.05
ALERTS_FILE: Final = "alerts.raw.json"
EVIDENCE_FILE: Final = "evidence.json"
TRIAGE_FILE: Final = "triage.json"
FINDINGS_FILE: Final = "findings.json"
SUMMARY_FILE: Final = "run.json"
EXCHANGES_FILE: Final = "exchanges.json"
AUTHZ_FILE: Final = "authz.json"
RULE_STATS_FILE: Final = "rule-stats.json"
METRICS_FILE: Final = "metrics.json"
_SCAN_MISSING_HINT: Final = (
    "O report precisa do scan.json (mesmo com authz.json). Uma execução só com probe, ou com "
    "'run --skip-scan', não o tem. Rode 'hdast scan PRODUTO --run RUN_ID' ou 'hdast run PRODUTO' "
    "sem --skip-scan, e confira o run_id e HDAST_RUNS_DIR."
)
KNOWN_FILES: Final = (
    "manifest.json",
    "audit.jsonl",
    "probe.json",
    EXCHANGES_FILE,
    AUTHZ_FILE,
    "scan-progress.json",
    SCAN_FILE,
    RULE_STATS_FILE,
    ALERTS_FILE,
    EVIDENCE_FILE,
    FINDINGS_FILE,
    "report.md",
    "report.html",
    METRICS_FILE,
    TRIAGE_FILE,
)
MAX_FILE_BYTES: Final = 64 * 1024 * 1024

_M = TypeVar("_M", bound=BaseModel)


class FileRunArtifacts:
    """Lê e grava os arquivos de uma execução no sistema de arquivos."""

    def __init__(self, runs_dir: Path) -> None:
        """Cria o armazém.

        Args:
            runs_dir: Pasta das execuções (`HDAST_RUNS_DIR`).
        """
        self._runs_dir = runs_dir

    def read_manifest(self, run_id: str) -> RunManifest:
        """Lê `manifest.json`."""
        return self._model(run_id, "manifest.json", RunManifest, "o probe")

    def read_probe(self, run_id: str) -> ProbeResult:
        """Lê `probe.json`."""
        return self._model(run_id, "probe.json", ProbeResult, "o probe")

    def read_scan(self, run_id: str) -> ScanResult:
        """Lê `scan.json`."""
        return self._model(run_id, SCAN_FILE, ScanResult, "o scan", missing_hint=_SCAN_MISSING_HINT)

    def read_findings(self, run_id: str) -> FindingsReport:
        """Lê `findings.json` de outra execução."""
        return self._model(run_id, FINDINGS_FILE, FindingsReport, "o report")

    def read_exchanges(self, run_id: str) -> ExchangeLog:
        """Lê `exchanges.json` (gravado pelo `probe`)."""
        return self._model(run_id, EXCHANGES_FILE, ExchangeLog, "o probe")

    def read_authz(self, run_id: str) -> AuthzResult | None:
        """Lê `authz.json`; `None` se o estágio não rodou nesta execução."""
        if not (self._directory(run_id) / AUTHZ_FILE).exists():
            return None
        return self._model(run_id, AUTHZ_FILE, AuthzResult, "o authz")

    def write_authz(self, run_id: str, result: AuthzResult) -> None:
        """Grava `authz.json`."""
        self._write(run_id, AUTHZ_FILE, result.model_dump_json(indent=2))

    def write_rule_stats(self, run_id: str, stats: RuleStatsFile) -> None:
        """Grava `rule-stats.json`."""
        self._write(run_id, RULE_STATS_FILE, stats.model_dump_json(indent=2))

    def read_rule_stats(self, run_id: str) -> RuleStatsFile | None:
        """Lê `rule-stats.json`; `None` se o `scan` não o gravou."""
        if not (self._directory(run_id) / RULE_STATS_FILE).exists():
            return None
        return self._model(run_id, RULE_STATS_FILE, RuleStatsFile, "o scan")

    def write_metrics(self, run_id: str, metrics: RunMetrics) -> None:
        """Grava `metrics.json`."""
        self._write(run_id, METRICS_FILE, metrics.model_dump_json(indent=2))

    def read_metrics(self, run_id: str) -> RunMetrics | None:
        """Lê `metrics.json`; `None` se a execução é anterior à medição."""
        if not (self._directory(run_id) / METRICS_FILE).exists():
            return None
        return self._model(run_id, METRICS_FILE, RunMetrics, "o report")

    def read_summary(self, run_id: str) -> RunSummary | None:
        """Lê `run.json`; `None` se a execução não passou pelo `hdast run`."""
        if not (self._directory(run_id) / SUMMARY_FILE).exists():
            return None
        return self._model(run_id, SUMMARY_FILE, RunSummary, "o run")

    def read_audit(self, run_id: str) -> tuple[AuditEntry, ...]:
        """Lê `audit.jsonl`; uma linha ilegível é erro (a trilha não pode ser adivinhada)."""
        text = self._read_text(run_id, "audit.jsonl", "o probe")
        try:
            return tuple(
                AuditEntry.model_validate_json(line) for line in text.splitlines() if line.strip()
            )
        except ValidationError:
            raise _corrupt("audit.jsonl", "o probe") from None

    def read_alerts(self, run_id: str) -> tuple[dict[str, object], ...]:
        """Lê `alerts.raw.json`."""
        data = self._json(run_id, ALERTS_FILE, "o scan")
        alerts = data.get("alerts") if isinstance(data, dict) else None
        if not isinstance(alerts, list) or not all(isinstance(item, dict) for item in alerts):
            raise _corrupt(ALERTS_FILE, "o scan")
        return tuple(item for item in alerts if isinstance(item, dict))

    def read_evidence(self, run_id: str) -> tuple[EvidenceMessage, ...]:
        """Lê `evidence.json`; vazio se o arquivo não existe."""
        if not (self._directory(run_id) / EVIDENCE_FILE).exists():
            return ()
        data = self._json(run_id, EVIDENCE_FILE, "o scan")
        items = data.get("messages") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise _corrupt(EVIDENCE_FILE, "o scan")
        try:
            return tuple(EvidenceMessage.model_validate(item) for item in items)
        except ValidationError:
            raise _corrupt(EVIDENCE_FILE, "o scan") from None

    def read_triage(self, run_id: str) -> object | None:
        """Lê `triage.json` como JSON bruto; `None` se não existe."""
        if not (self._directory(run_id) / TRIAGE_FILE).exists():
            return None
        return self._json(run_id, TRIAGE_FILE, "a triagem")

    def write_scan(self, run_id: str, result: ScanResult) -> None:
        """Grava `scan.json`."""
        self._write(run_id, SCAN_FILE, result.model_dump_json(indent=2))

    def write_progress(self, run_id: str, progress: ScanProgress) -> None:
        """Grava `scan-progress.json`."""
        self._write(run_id, PROGRESS_FILE, progress.model_dump_json(indent=2))

    def write_alerts(self, run_id: str, alerts: Sequence[dict[str, str]]) -> None:
        """Grava `alerts.raw.json` (alertas já redigidos)."""
        payload = {"schema_version": 1, "run_id": run_id, "alerts": list(alerts)}
        self._write(run_id, ALERTS_FILE, json.dumps(payload, indent=2, ensure_ascii=False))

    def write_evidence(self, run_id: str, messages: Sequence[EvidenceMessage]) -> None:
        """Grava `evidence.json` (mensagens já redigidas)."""
        payload = {
            "schema_version": 1,
            "run_id": run_id,
            "messages": [message.model_dump(mode="json") for message in messages],
        }
        self._write(run_id, EVIDENCE_FILE, json.dumps(payload, indent=2, ensure_ascii=False))

    def running(self) -> tuple[ScanProgress, ...]:
        """Andamentos `running` de todas as execuções (arquivo ilegível é ignorado)."""
        found: list[ScanProgress] = []
        for path in sorted(self._runs_dir.glob(f"*/{PROGRESS_FILE}")):
            try:
                progress = ScanProgress.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if progress.status == "running":
                found.append(progress)
        return tuple(found)

    def write_summary(self, run_id: str, summary: RunSummary) -> None:
        """Grava `run.json`."""
        self._write(run_id, SUMMARY_FILE, summary.model_dump_json(indent=2))

    def existing_files(self, run_id: str) -> dict[str, str]:
        """Artefatos conhecidos que existem na pasta da execução (nome -> nome do arquivo)."""
        directory = self._directory(run_id)
        return {name: name for name in KNOWN_FILES if (directory / name).is_file()}

    def _directory(self, run_id: str) -> Path:
        return self._runs_dir / require_run_id(run_id)

    def _read_text(
        self, run_id: str, name: str, command: str, missing_hint: str | None = None
    ) -> str:
        path = self._directory(run_id) / name
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise _corrupt(name, command)
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ConfigError(
                f"A execução não tem {name}.",
                hint=missing_hint
                or f"Rode {command} nesta execução (ou confira o run_id e HDAST_RUNS_DIR).",
            ) from None
        except (OSError, UnicodeDecodeError):
            raise _corrupt(name, command) from None

    def _json(
        self, run_id: str, name: str, command: str, missing_hint: str | None = None
    ) -> object:
        try:
            parsed: object = json.loads(self._read_text(run_id, name, command, missing_hint))
        except (ValueError, RecursionError):
            raise _corrupt(name, command) from None
        return parsed

    def _model(
        self,
        run_id: str,
        name: str,
        model: type[_M],
        command: str,
        missing_hint: str | None = None,
    ) -> _M:
        try:
            return model.model_validate(self._json(run_id, name, command, missing_hint))
        except ValidationError:
            raise _corrupt(name, command) from None

    def _write(self, run_id: str, name: str, text: str) -> None:
        directory = self._directory(run_id)
        target = directory / name
        temporary = directory / f".{name}.tmp"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            temporary.write_text(text + "\n", encoding="utf-8", newline="\n")
            _replace_with_retry(temporary, target)
        except OSError:
            raise ConfigError(
                f"Não foi possível gravar {name} da execução.",
                hint="Confira HDAST_RUNS_DIR, o espaço em disco e a permissão de escrita.",
            ) from None


def _replace_with_retry(source: Path, target: Path) -> None:
    """`os.replace` que tolera um leitor passando pelo arquivo.

    No Windows, trocar um arquivo que outro processo tem aberto (`hdast stop`, a pessoa ou o
    coordenador acompanhando `scan-progress.json`, antivírus) levanta `PermissionError`; sem isto
    uma leitura de cortesia derrubava a varredura inteira. Tenta poucas vezes e só então desiste.
    """
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(source, target)
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_PAUSE_SECONDS * (attempt + 1))
        else:
            return


def _corrupt(name: str, command: str) -> ConfigError:
    return ConfigError(
        f"O arquivo {name} da execução está ilegível ou fora do formato esperado.",
        hint=f"Refaça {command} para gerá-lo de novo.",
    )
