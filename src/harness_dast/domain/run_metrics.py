"""Medição de uma execução (`metrics.json`, ADR 0031): onde o tempo foi. Módulo puro.

Só números e identificadores: nenhum dado do alvo, nenhum segredo, nenhuma URL. O módulo junta
o que as etapas já gravaram (`manifest.json`, `probe.json`, `scan.json`, `authz.json`,
`rule-stats.json`), o resumo do `run`, quando há, e as linhas da auditoria do proxy, quando há.
Não calcula de novo o que já está pronto: duração e pedidos por operação vêm de `scan.json`, o
total de tráfego vem de `scan.traffic`. Etapa que não rodou fica `None`, nunca zero.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Final, Literal

from pydantic import Field

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.rule_stats import RuleStat, RuleStatsFile, RuleTotal, total_rules
from harness_dast.domain.run_summary import StageName, StageRecord
from harness_dast.domain.scan_policy import DEFAULT_DISABLED_RULES
from harness_dast.domain.scan_result import ScanEntry, ScanResult
from harness_dast.domain.traffic import ProxyRow, TrafficGaps, find_gaps

METRICS_SCHEMA_VERSION: Final = 1
_MEASURED: Final = frozenset({"ok", "failed", "interrupted"})
_NO_FILE: Final = (
    "O scan não gravou rule-stats.json para esta varredura (execução anterior à medição)."
)
_NOT_STARTED: Final = "A varredura desta operação não chegou a começar."


class StageSeconds(ApiModel):
    """Duração de cada etapa em segundos; `None` quando a etapa não rodou ou não foi medida."""

    preflight: float | None = None
    probe: float | None = None
    scan: float | None = None
    authz: float | None = None
    negative: float | None = None
    report: float | None = None


class OperationMetric(ApiModel):
    """Medição de uma operação varrida.

    Attributes:
        operation_id: Operação.
        outcome: Resultado da varredura (`completed`, `truncated`, `stopped`, `refused`).
        duration_seconds: Duração medida pela CLI (de `scan.json`).
        requests: Pedidos que o ZAP enviou (de `scan.json`).
        rules_available: Se a medição por regra desta operação existe.
        rules_unavailable_reason: Por que não existe, quando não existe.
        rules: Medição de cada regra nesta operação.
    """

    operation_id: str
    outcome: str
    duration_seconds: float
    requests: int
    rules_available: bool
    rules_unavailable_reason: str | None = None
    rules: tuple[RuleStat, ...] = ()


class RuleMetrics(ApiModel):
    """As regras somadas na execução inteira.

    Attributes:
        operations_measured: Varreduras com medição por regra.
        operations_unavailable: Varreduras sem a medição (coleta falhou ou não houve).
        totals: Uma linha por regra, da mais lenta para a mais rápida.
    """

    operations_measured: int = 0
    operations_unavailable: int = 0
    totals: tuple[RuleTotal, ...] = ()


class TrafficMetrics(ApiModel):
    """Tráfego que o proxy de escopo viu durante o `scan` (de `scan.traffic`) e as lacunas.

    Attributes:
        available: Se havia auditoria do proxy (pilha gerenciada).
        allowed: Pedidos liberados.
        denied: Pedidos recusados.
        denied_by_reason: Recusas por motivo.
        denied_by_detail: Recusas por motivo granular.
        gaps: Silêncios longos do tráfego; `None` sem a auditoria do proxy.
    """

    available: bool = False
    allowed: int = 0
    denied: int = 0
    denied_by_reason: dict[str, int] = Field(default_factory=dict)
    denied_by_detail: dict[str, int] = Field(default_factory=dict)
    gaps: TrafficGaps | None = None


class DisabledRuleMetric(ApiModel):
    """Regra desligada pela política do `scan`.

    Attributes:
        plugin_id: Identificador da regra no ZAP.
        name: Nome, quando o harness o conhece (as de `DEFAULT_DISABLED_RULES`).
        reason: Por que está desligada.
        source: `default` (política do harness) ou `profile` (`scan.disable_rules` do perfil).
    """

    plugin_id: int
    name: str | None = None
    reason: str
    source: Literal["default", "profile"]


class TimingMetrics(ApiModel):
    """Tempos somados, que podem se sobrepor; ausência significa não medido."""

    local_queue_seconds: float | None = None
    authentication_seconds: float | None = None
    zap_delay_seconds: float | None = None
    proxy_grant_wait_seconds: float | None = None
    proxy_network_seconds: float | None = None
    cpu_seconds: float | None = None
    memory_peak_bytes: int | None = None


def _timing(scan: ScanResult | None, rows: Sequence[ProxyRow] | None) -> TimingMetrics:
    selected: list[ProxyRow] = []
    if scan is not None and rows is not None:
        start, end = _moment(scan.started_at), _moment(scan.finished_at)
        if start is not None and end is not None:
            selected = [r for r in rows if start <= r.at <= end and r.decision == "allow"]
    waits = [r.grant_wait_ms for r in selected]
    network = [r.network_ms for r in selected]
    return TimingMetrics(
        local_queue_seconds=scan.local_queue_seconds if scan else None,
        authentication_seconds=scan.authentication_seconds if scan else None,
        zap_delay_seconds=scan.zap_delay_seconds if scan else None,
        cpu_seconds=scan.process_cpu_seconds if scan else None,
        memory_peak_bytes=scan.process_peak_memory_bytes if scan else None,
        proxy_grant_wait_seconds=round(sum(x for x in waits if x is not None) / 1000, 3)
        if waits and all(x is not None for x in waits)
        else None,
        proxy_network_seconds=round(sum(x for x in network if x is not None) / 1000, 3)
        if network and all(x is not None for x in network)
        else None,
    )


class RunMetrics(ApiModel):
    """Conteúdo de `metrics.json`.

    Attributes:
        schema_version: Versão do formato; só cresce com campos aditivos.
        run_id: Execução.
        product: Produto.
        harness_version: Versão do `hdast` que gravou.
        zap_version: Versão do ZAP, quando o `scan` a conheceu.
        path_mode: Modo de leitura do caminho (`strict` ou `wide`).
        started_at: Início da execução (ISO 8601).
        finished_at: Fim (ISO 8601), ou `None` se não há fim conhecido.
        generated_at: Quando este arquivo foi gravado.
        stages_seconds: Duração por etapa.
        scan_status: Estado final do `scan` (`completed` ou o motivo da parada), ou `None`.
        operations: Uma linha por operação varrida.
        rules: Regras somadas.
        traffic: Tráfego e lacunas.
        disabled_rules: Regras desligadas pela política.
    """

    schema_version: int = METRICS_SCHEMA_VERSION
    run_id: str
    product: str
    harness_version: str
    zap_version: str | None = None
    path_mode: str
    started_at: str
    finished_at: str | None = None
    generated_at: str
    stages_seconds: StageSeconds
    scan_status: str | None = None
    operations: tuple[OperationMetric, ...] = ()
    rules: RuleMetrics = Field(default_factory=RuleMetrics)
    traffic: TrafficMetrics = Field(default_factory=TrafficMetrics)
    timing: TimingMetrics = Field(default_factory=TimingMetrics)
    disabled_rules: tuple[DisabledRuleMetric, ...] = ()


def _moment(text: str | None) -> datetime | None:
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _span(start: str | None, finish: str | None) -> float | None:
    begin, end = _moment(start), _moment(finish)
    if begin is None or end is None:
        return None
    return round((end - begin).total_seconds(), 3)


def _from_summary(record: StageRecord | None) -> float | None:
    if record is None or record.status not in _MEASURED:
        return None
    return record.duration_seconds


def stage_seconds(
    *,
    probe: ProbeResult | None,
    scan: ScanResult | None,
    authz: AuthzResult | None,
    report_seconds: float | None,
    stages: Sequence[StageRecord] | None,
    negative: NegativeResult | None = None,
) -> StageSeconds:
    """Duração por etapa: o registro do `run` manda (inclui o preparo); senão, os arquivos.

    Com o registro do `run`, etapa pulada ou que não rodou fica `None`, mesmo que haja arquivo
    antigo.
    """
    records = {record.name: record for record in stages} if stages else {}
    derived: dict[StageName, float | None] = {
        "preflight": None,
        "probe": None
        if probe is None or probe.dry_run
        else _span(probe.started_at, probe.finished_at),
        "scan": None if scan is None or scan.dry_run else _span(scan.started_at, scan.finished_at),
        "authz": None if authz is None else _span(authz.started_at, authz.finished_at),
        "negative": None if negative is None else _span(negative.started_at, negative.finished_at),
        "report": report_seconds,
    }
    return StageSeconds(
        **{
            name: _from_summary(records[name]) if name in records else value
            for name, value in derived.items()
        }
    )


def _operation(entry: ScanEntry, rules: RuleStatsFile | None) -> OperationMetric:
    reason: str | None = None
    found: tuple[RuleStat, ...] = ()
    if entry.scan_id is None:
        reason = _NOT_STARTED
    elif rules is None:
        reason = _NO_FILE
    else:
        match = next((op for op in rules.operations if op.scan_id == entry.scan_id), None)
        if match is None:
            reason = _NO_FILE
        elif match.unavailable_reason is not None:
            reason = match.unavailable_reason
        else:
            found = match.rules
    return OperationMetric(
        operation_id=entry.operation_id,
        outcome=entry.outcome,
        duration_seconds=entry.duration_seconds,
        requests=entry.requests,
        rules_available=reason is None,
        rules_unavailable_reason=reason,
        rules=found,
    )


def _rule_metrics(operations: Sequence[OperationMetric]) -> RuleMetrics:
    measured = [op for op in operations if op.rules_available]
    return RuleMetrics(
        operations_measured=len(measured),
        operations_unavailable=len(operations) - len(measured),
        totals=total_rules([op.rules for op in measured]),
    )


def _disabled(scan: ScanResult | None) -> tuple[DisabledRuleMetric, ...]:
    if scan is None:
        return ()
    known = {rule.plugin_id: rule for rule in DEFAULT_DISABLED_RULES}
    return tuple(
        DisabledRuleMetric(
            plugin_id=plugin_id, name=rule.name, reason=rule.reason, source="default"
        )
        if (rule := known.get(plugin_id)) is not None
        else DisabledRuleMetric(
            plugin_id=plugin_id,
            reason="Desligada pela pessoa dona do perfil (scan.disable_rules).",
            source="profile",
        )
        for plugin_id in scan.policy.disabled_rules
    )


def _traffic(scan: ScanResult | None, rows: Sequence[ProxyRow] | None) -> TrafficMetrics:
    if scan is None or not scan.traffic.enabled:
        return TrafficMetrics()
    return TrafficMetrics(
        available=True,
        allowed=scan.traffic.allowed,
        denied=scan.traffic.denied,
        denied_by_reason=scan.traffic.denied_by_reason,
        denied_by_detail=scan.traffic.denied_by_detail,
        gaps=_gaps(scan, rows),
    )


def _gaps(scan: ScanResult, rows: Sequence[ProxyRow] | None) -> TrafficGaps | None:
    start, end = _moment(scan.started_at), _moment(scan.finished_at)
    if rows is None or start is None or end is None:
        return None
    # Sem nenhuma linha dentro do scan, a trilha é de outra pilha: "0 lacunas" seria mentira.
    if not any(start <= row.at <= end for row in rows):
        return None
    return find_gaps(rows, start=start, end=end)


def _window(
    manifest: RunManifest,
    run_window: tuple[str, str] | None,
    stamps: Sequence[str | None],
) -> tuple[str, str | None]:
    """Início e fim da execução: o `run` manda; senão, o manifesto e o último arquivo."""
    if run_window is not None:
        return run_window
    ends = sorted(
        (moment, text) for text in stamps if text and (moment := _moment(text)) is not None
    )
    return manifest.started_at, ends[-1][1] if ends else None


def build_run_metrics(
    *,
    manifest: RunManifest,
    probe: ProbeResult | None,
    scan: ScanResult | None,
    authz: AuthzResult | None,
    negative: NegativeResult | None = None,
    rule_stats: RuleStatsFile | None,
    proxy_rows: Sequence[ProxyRow] | None,
    stages: Sequence[StageRecord] | None,
    run_window: tuple[str, str] | None,
    report_seconds: float | None,
    path_mode: str,
    harness_version: str,
    generated_at: str,
) -> RunMetrics:
    """Monta o `metrics.json` com o que existe; o que falta fica `None` ou indisponível.

    Args:
        manifest: `manifest.json` (obrigatório: dá produto e início).
        probe: `probe.json`, se existe.
        scan: `scan.json`, se existe.
        authz: `authz.json`, se o estágio rodou.
        negative: `negative.json`, se o estágio rodou.
        rule_stats: `rule-stats.json`, se existe.
        proxy_rows: Linhas da auditoria do proxy; `None` sem pilha gerenciada.
        stages: Registro dos estágios do `hdast run`, quando o chamador o tem.
        run_window: (início, fim) da execução do `hdast run`, quando o chamador o tem.
        report_seconds: Duração do `report` quando chamado por ele.
        path_mode: Modo de caminho do perfil.
        harness_version: Versão do `hdast`.
        generated_at: Instante da gravação (do relógio injetado).
    """
    started, finished = _window(
        manifest,
        run_window,
        [
            probe.finished_at if probe else None,
            scan.finished_at if scan else None,
            authz.finished_at if authz else None,
            negative.finished_at if negative else None,
        ],
    )
    operations = tuple(_operation(entry, rule_stats) for entry in scan.entries) if scan else ()
    return RunMetrics(
        run_id=manifest.run_id,
        product=manifest.product,
        harness_version=harness_version,
        zap_version=(rule_stats.zap_version if rule_stats else None) or manifest.zap_version,
        path_mode=path_mode,
        started_at=started,
        finished_at=finished,
        generated_at=generated_at,
        stages_seconds=stage_seconds(
            probe=probe,
            scan=scan,
            authz=authz,
            negative=negative,
            report_seconds=report_seconds,
            stages=stages,
        ),
        scan_status=scan.status if scan and not scan.dry_run else None,
        operations=operations,
        rules=_rule_metrics(operations),
        traffic=_traffic(scan, proxy_rows),
        timing=_timing(scan, proxy_rows),
        disabled_rules=_disabled(scan),
    )
