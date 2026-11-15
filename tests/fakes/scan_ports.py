"""Falsos em memória das portas de `scan` e `report`, com comportamento.

`FakeScanZap` estende o `FakeZap` do `probe` (regras do Replacer compartilhadas) e simula as
varreduras: cada `start_scan` cria uma varredura que avança a cada consulta de estado.
`InMemoryRunArtifacts` guarda o que o `scan` grava e lê o que o `probe` gravou no
`InMemoryRunStore`.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from harness_dast.application.scan_ports import ScanStart
from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.errors import ConfigError, ExternalToolError
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.redaction import EvidenceMessage
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.rule_stats import RuleStat, RuleStatsFile
from harness_dast.domain.run_metrics import RunMetrics
from harness_dast.domain.scan_policy import ScanLimits, ScanPolicy
from harness_dast.domain.scan_result import ScanProgress, ScanRefused, ScanResult, ScanStatus
from harness_dast.domain.scan_tokens import ReplacerRule
from harness_dast.domain.signal_result import ProxySignals
from harness_dast.domain.traffic import ProxyRow
from harness_dast.domain.zap_messages import ZapMessage
from tests.fakes.probe_ports import FakeTarget, FakeZap, InMemoryRunStore

DEFAULT_RULE_STATS = (
    RuleStat(plugin_id=40018, name="SQL Injection", state="completed", time_ms=1200, requests=40),
    RuleStat(
        plugin_id=40026,
        name="Cross Site Scripting (DOM Based)",
        state="skipped",
        time_ms=25,
        skip_reason="other",
    ),
)

type AlertFactory = Callable[[ScanStart, "FakeScanZap"], list[dict[str, str]]]


@dataclass
class _Scan:
    request: ScanStart
    polls: int = 0
    stopped: bool = False
    alerts: int = 0


@dataclass
class FakeScanZap(FakeZap):
    """`ScanControl` falso por cima do `FakeZap`; guarda tudo o que recebeu.

    Attributes:
        calls: Eventos em ordem (`apply_policy`, `start_scan:GET`, `stop_scan`...).
        started: Pedidos de varredura recebidos.
        rule_log: (`add` ou `remove`, nome da regra) em ordem.
        installed: Regras instaladas agora (nome -> regra).
        ever_installed: Toda regra já instalada (nome -> regra), mesmo depois de removida.
        rules_at_start: Nomes das regras instaladas no instante de cada `start_scan`.
        messages: Histórico do ZAP (mensagens aprendidas e de ataque).
        alerts: Alertas da sessão.
        context: (nome, id) do contexto existente.
        script: Progresso a devolver a cada consulta, por varredura.
        alert_factory: Alertas que cada varredura gera ao iniciar.
        on_status: Gancho chamado a cada consulta (id da varredura, número da consulta).
        refuse: Se não vazio, o ZAP recusa as varreduras cujo `method` está aqui.
        failures: Falha a levantar na chamada com este nome de método.
        let_through: Quantas chamadas daquele método passam antes de a falha começar.
        policy_state: Regras que o ZAP "esquece" de desligar (testa a verificação).
        rule_stats: Medição por regra que `scan_rules` devolve para toda varredura.
    """

    calls: list[str] = field(default_factory=list)
    started: list[ScanStart] = field(default_factory=list)
    rule_log: list[tuple[str, str]] = field(default_factory=list)
    installed: dict[str, ReplacerRule] = field(default_factory=dict)
    ever_installed: dict[str, ReplacerRule] = field(default_factory=dict)
    rules_at_start: list[list[str]] = field(default_factory=list)
    messages: dict[int, ZapMessage] = field(default_factory=dict)
    alerts: list[dict[str, str]] = field(default_factory=list)
    context: tuple[str, int] | None = None
    script: list[tuple[int, str]] = field(
        default_factory=lambda: [(50, "RUNNING"), (100, "FINISHED")]
    )
    alert_factory: AlertFactory | None = None
    on_status: Callable[[str, int], None] | None = None
    refuse: frozenset[str] = frozenset()
    failures: dict[str, ExternalToolError | BaseException] = field(default_factory=dict)
    ignore_disable: bool = False
    applied: list[tuple[ScanPolicy, ScanLimits]] = field(default_factory=list)
    options_before_first_scan: bool = False
    let_through: dict[str, int] = field(default_factory=dict)
    rule_stats: tuple[RuleStat, ...] = DEFAULT_RULE_STATS
    _scans: dict[str, _Scan] = field(default_factory=dict)
    _seen: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        FakeZap.__init__(self)

    def _fail(self, name: str) -> None:
        self.calls.append(name)
        failure = self.failures.get(name)
        if failure is None:
            return
        seen = self._seen.get(name, 0)
        self._seen[name] = seen + 1
        if seen >= self.let_through.get(name, 0):
            raise failure

    def learn_from(self, target: FakeTarget, store: InMemoryRunStore, run_id: str) -> None:
        """Registra como mensagens do ZAP as requisições do `probe` que saíram pela rota `zap`."""
        sent = [r for r in target.requests if r.route == "zap"]
        statuses = [
            entry.status
            for entry in store.audit.get(run_id, [])
            if entry.phase == "result" and entry.route == "zap"
        ]
        for index, (request, status) in enumerate(zip(sent, statuses, strict=False), start=1):
            headers = "".join(f"{k}: {v}\r\n" for k, v in request.headers)
            self.messages[index] = ZapMessage(
                id=index,
                type="1",
                request_header=f"{request.method} {request.url} HTTP/1.1\r\n{headers}",
                request_body=(request.body or b"").decode(),
                response_header=f"HTTP/1.1 {status} OK\r\n",
                response_body="{}",
            )

    def verify_context(self, name: str, context_id: int) -> None:
        self._fail("verify_context")
        if self.context != (name, context_id):
            raise ExternalToolError(
                "O contexto desta execução não existe no ZAP com o id registrado.",
                hint="Refaça o probe.",
            )

    def list_messages(self, base_url: str) -> tuple[ZapMessage, ...]:
        self._fail("list_messages")
        return tuple(m for m in self.messages.values() if m.type == "1")

    def get_message(self, message_id: int) -> ZapMessage:
        self._fail("get_message")
        if message_id not in self.messages:
            raise ExternalToolError("Mensagem inexistente.")
        return self.messages[message_id]

    def apply_policy(self, policy: ScanPolicy, limits: ScanLimits) -> None:
        self._fail("apply_policy")
        self.applied.append((policy, limits))
        if self.ignore_disable:
            raise ExternalToolError("Regras que deviam estar desligadas continuam ligadas: 40044.")

    def start_scan(self, request: ScanStart) -> str:
        self._fail("start_scan")
        self.calls.append(f"start_scan:{request.method}")
        if request.method in self.refuse:
            raise ScanRefused("O ZAP recusou iniciar a varredura (url_not_in_context).")
        scan_id = str(len(self._scans))
        self.started.append(request)
        self.rules_at_start.append(sorted(self.installed))
        scan = _Scan(request)
        if self.alert_factory is not None:
            for alert in self.alert_factory(request, self):
                alert.setdefault("id", str(len(self.alerts) + 1))
                self.alerts.append(alert)
                scan.alerts += 1
        self._scans[scan_id] = scan
        return scan_id

    def scan_status(self, scan_id: str) -> ScanStatus:
        self._fail("scan_status")
        scan = self._scans[scan_id]
        if self.on_status is not None:
            self.on_status(scan_id, scan.polls)
        progress, state = self.script[min(scan.polls, len(self.script) - 1)]
        scan.polls += 1
        return ScanStatus(
            scan_id=scan_id,
            state=state,
            progress=progress,
            requests=progress * 3,
            alerts=scan.alerts,
        )

    def scan_rules(self, scan_id: str) -> tuple[RuleStat, ...]:
        self._fail("scan_rules")
        if scan_id not in self._scans:
            raise ExternalToolError("Varredura desconhecida.")
        return self.rule_stats

    def stop_scan(self, scan_id: str) -> None:
        self._fail("stop_scan")
        self._scans[scan_id].stopped = True

    def list_alerts(self, base_url: str) -> tuple[dict[str, str], ...]:
        self._fail("list_alerts")
        return tuple(dict(alert) for alert in self.alerts)

    def add_replacer_rule(self, rule: ReplacerRule) -> None:
        self._fail("add_replacer_rule")
        self.rule_log.append(("add", rule.description))
        self.installed[rule.description] = rule
        self.ever_installed[rule.description] = rule
        self.rules.append(rule.description)

    def remove_replacer_rule(self, description: str) -> None:
        self._fail("remove_replacer_rule")
        if description not in self.installed:
            raise ExternalToolError("A API do ZAP recusou removeRule (código does_not_exist).")
        self.rule_log.append(("remove", description))
        del self.installed[description]
        self.rules = [name for name in self.rules if name != description]

    def remove_stale_rules(self, prefix: str) -> int:
        self._fail("remove_stale_rules")
        for name in [n for n in self.installed if n.startswith(prefix)]:
            del self.installed[name]
        return super().remove_stale_rules(prefix)

    def remove_scan_policy(self, name: str) -> None:
        self._fail("remove_scan_policy")

    def was_stopped(self, scan_id: str) -> bool:
        """Se a varredura recebeu `stop_scan`."""
        return self._scans[scan_id].stopped

    @property
    def running(self) -> list[str]:
        """Varreduras que ainda não foram paradas nem consultadas até o fim."""
        return [sid for sid, scan in self._scans.items() if not scan.stopped and scan.polls == 0]


class FakeProxyAudit:
    """`ProxyAudit` falso: devolve as linhas dadas, ou levanta o erro dado."""

    def __init__(self, rows: tuple[ProxyRow, ...] = (), error: ConfigError | None = None) -> None:
        self._rows = rows
        self._error = error

    def rows(self) -> tuple[ProxyRow, ...]:
        if self._error is not None:
            raise self._error
        return self._rows


class InMemoryRunArtifacts:
    """`RunArtifacts` falso sobre o `InMemoryRunStore` do `probe`."""

    def __init__(self, store: InMemoryRunStore) -> None:
        self._store = store
        self.scans: dict[str, ScanResult] = {}
        self.progress: dict[str, list[ScanProgress]] = {}
        self.alerts: dict[str, list[dict[str, str]]] = {}
        self.evidence: dict[str, list[EvidenceMessage]] = {}
        self.triage: dict[str, object] = {}
        self.findings: dict[str, FindingsReport] = {}
        self.authz: dict[str, AuthzResult] = {}
        self.negative: dict[str, NegativeResult] = {}
        self.rule_stats: dict[str, RuleStatsFile] = {}
        self.metrics: dict[str, RunMetrics] = {}
        self.signals: dict[str, ProxySignals] = {}
        self.failing_writes: set[str] = set()

    def read_manifest(self, run_id: str) -> RunManifest:
        if run_id not in self._store.manifests:
            raise ConfigError("A execução não tem manifest.json.")
        return self._store.manifests[run_id][-1]

    def read_probe(self, run_id: str) -> ProbeResult:
        if run_id not in self._store.probes:
            raise ConfigError("A execução não tem probe.json.")
        return self._store.probes[run_id]

    def read_audit(self, run_id: str) -> tuple[AuditEntry, ...]:
        return tuple(self._store.audit.get(run_id, []))

    def write_scan(self, run_id: str, result: ScanResult) -> None:
        self.scans[run_id] = result

    def write_progress(self, run_id: str, progress: ScanProgress) -> None:
        self.progress.setdefault(run_id, []).append(progress)

    def write_alerts(self, run_id: str, alerts: Any) -> None:
        self.alerts[run_id] = [dict(alert) for alert in alerts]

    def write_evidence(self, run_id: str, messages: Any) -> None:
        self.evidence[run_id] = list(messages)

    def read_scan(self, run_id: str) -> ScanResult:
        if run_id not in self.scans:
            raise ConfigError("A execução não tem scan.json.")
        return self.scans[run_id]

    def read_alerts(self, run_id: str) -> tuple[dict[str, object], ...]:
        if run_id not in self.alerts:
            raise ConfigError("A execução não tem alerts.raw.json.")
        return tuple(dict(alert) for alert in self.alerts[run_id])

    def read_evidence(self, run_id: str) -> tuple[EvidenceMessage, ...]:
        return tuple(self.evidence.get(run_id, []))

    def read_triage(self, run_id: str) -> object | None:
        return self.triage.get(run_id)

    def read_findings(self, run_id: str) -> FindingsReport:
        if run_id not in self.findings:
            raise ConfigError("A execução não tem findings.json.")
        return self.findings[run_id]

    def read_authz(self, run_id: str) -> AuthzResult | None:
        return self.authz.get(run_id)

    def read_negative(self, run_id: str) -> NegativeResult | None:
        return self.negative.get(run_id)

    def write_authz(self, run_id: str, result: AuthzResult) -> None:
        self.authz[run_id] = result

    def read_signals(self, run_id: str) -> ProxySignals | None:
        return self.signals.get(run_id)

    def write_signals(self, run_id: str, signals: ProxySignals) -> None:
        if "signals" in self.failing_writes:
            raise ConfigError("Falha simulada ao gravar error-signals.json.")
        self.signals[run_id] = signals

    def write_negative(self, run_id: str, result: NegativeResult) -> None:
        self.negative[run_id] = result

    def write_rule_stats(self, run_id: str, stats: RuleStatsFile) -> None:
        if "rule_stats" in self.failing_writes:
            raise ConfigError("disco cheio")
        self.rule_stats[run_id] = stats

    def read_rule_stats(self, run_id: str) -> RuleStatsFile | None:
        return self.rule_stats.get(run_id)

    def write_metrics(self, run_id: str, metrics: RunMetrics) -> None:
        if "metrics" in self.failing_writes:
            raise ConfigError("disco cheio")
        self.metrics[run_id] = metrics

    def read_exchanges(self, run_id: str) -> ExchangeLog:
        if run_id not in self._store.exchanges:
            raise ConfigError("A execução não tem exchanges.json.")
        return self._store.exchanges[run_id]

    def serialized(self) -> str:
        """Tudo o que o `scan` gravou, como texto (para procurar vazamentos)."""
        parts = [r.model_dump_json() for r in self.scans.values()]
        parts += [p.model_dump_json() for ps in self.progress.values() for p in ps]
        parts += [json.dumps(a) for alerts in self.alerts.values() for a in alerts]
        parts += [m.model_dump_json() for ms in self.evidence.values() for m in ms]
        parts += [a.model_dump_json() for a in self.authz.values()]
        parts += [n.model_dump_json() for n in self.negative.values()]
        parts += [r.model_dump_json() for r in self.rule_stats.values()]
        parts += [m.model_dump_json() for m in self.metrics.values()]
        return "\n".join(parts)
