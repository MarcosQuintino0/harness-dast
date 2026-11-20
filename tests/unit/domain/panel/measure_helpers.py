"""Cenários de medição e de cerca para testar as abas Cobertura e Tempo e tokens."""

from typing import Any

from harness_dast.domain.agent_metrics import (
    AgentMetrics,
    AgentStageMetrics,
    AgentTokens,
    AgentTotals,
)
from harness_dast.domain.panel.model import PanelView
from harness_dast.domain.panel.sources import PanelSources
from harness_dast.domain.rule_stats import RuleStat, RuleTotal
from harness_dast.domain.run_metrics import (
    DisabledRuleMetric,
    OperationMetric,
    RuleMetrics,
    RunMetrics,
    StageSeconds,
    TrafficMetrics,
)
from harness_dast.domain.traffic import TrafficGaps, TrafficSummary
from tests.unit.domain.panel.helpers import PRODUCT, sources, view
from tests.unit.domain.report.helpers import RUN_ID


def traffic(**changes: Any) -> TrafficSummary:
    """Tráfego medido, com os números da rodada real (16.854 pedidos, 8.651 barrados)."""
    base: dict[str, Any] = {
        "enabled": True,
        "allowed": 8203,
        "denied": 8651,
        "denied_by_reason": {
            "malformed_request": 7538,
            "path_not_allowed": 1087,
            "origin_not_allowed": 26,
        },
        "denied_by_detail": {
            "path_encoded_slash": 2608,
            "path_not_allowed": 1087,
            "path_dot_segment": 52,
            "path_empty_segment": 328,
            "path_matrix_param": 1444,
            "path_double_encoding": 905,
            "path_trailing_dot_space": 1355,
            "path_control_char": 846,
            "origin_not_allowed": 26,
        },
        "path_shape_denied": 7538,
        "allowed_outside_allow": 0,
        "path_mode": "strict",
    }
    base.update(changes)
    return TrafficSummary(**base)


def with_traffic(**changes: Any) -> PanelSources:
    """O cenário padrão com a cerca medida."""
    base = sources()
    scan = base.scan.model_copy(update={"traffic": traffic(**changes)})  # type: ignore[union-attr]
    return sources(scan=scan)


def rule_total(plugin_id: int, name: str, time_ms: int, **changes: Any) -> RuleTotal:
    base: dict[str, Any] = {
        "plugin_id": plugin_id,
        "name": name,
        "time_ms": time_ms,
        "requests": 63,
        "alerts": 0,
        "operations": 2,
        "completed": 2,
        "skipped": 0,
        "interrupted": 0,
        "pending": 0,
        "unknown": 0,
    }
    base.update(changes)
    return RuleTotal(**base)


def run_metrics(**changes: Any) -> RunMetrics:
    """`metrics.json` com duas operações, três regras, lacunas e uma regra desligada."""
    operations = (
        OperationMetric(
            operation_id="obter",
            outcome="completed",
            duration_seconds=56.0,
            requests=120,
            rules_available=True,
            rules=(
                RuleStat(plugin_id=40018, name="SQL Injection", state="completed", time_ms=6000),
                RuleStat(
                    plugin_id=90020,
                    name="Remote OS Command Injection",
                    state="skipped",
                    skip_reason="max_rule_time",
                ),
                RuleStat(plugin_id=6, name="Path Traversal", state="interrupted"),
            ),
        ),
        OperationMetric(
            operation_id="listar",
            outcome="completed",
            duration_seconds=5.0,
            requests=40,
            rules_available=False,
            rules_unavailable_reason="coleta falhou",
        ),
    )
    base: dict[str, Any] = {
        "run_id": RUN_ID,
        "product": PRODUCT,
        "harness_version": "1.2",
        "zap_version": "2.17",
        "path_mode": "strict",
        "started_at": "2026-11-13T23:08:00+00:00",
        "generated_at": "2026-11-13T23:40:00+00:00",
        "stages_seconds": StageSeconds(probe=20.0, scan=1140.0, report=2.0),
        "operations": operations,
        "rules": RuleMetrics(
            operations_measured=1,
            operations_unavailable=1,
            totals=(
                rule_total(40018, "SQL Injection", 6000, alerts=2),
                rule_total(6, "Path Traversal", 400),
                rule_total(90020, "Remote OS Command Injection", 0, completed=0, skipped=1),
            ),
        ),
        "traffic": TrafficMetrics(
            available=True,
            allowed=8203,
            denied=8651,
            gaps=TrafficGaps(count=2, total_seconds=49.0, longest_seconds=30.0),
        ),
        "disabled_rules": (
            DisabledRuleMetric(
                plugin_id=30001, name="Buffer Overflow", reason="Destrutiva.", source="default"
            ),
            DisabledRuleMetric(plugin_id=99, reason="Pedido do perfil.", source="profile"),
        ),
    }
    base.update(changes)
    return RunMetrics(**base)


def agent_metrics(**changes: Any) -> AgentMetrics:
    """`agent-metrics.json` com as etapas do agente e um modelo."""

    def stage(inp: int, out: int, cache: int, read: int = 1000) -> AgentStageMetrics:
        return AgentStageMetrics(
            tokens=AgentTokens(input=inp, output=out, cache_creation=cache, cache_read=read)
        )

    base: dict[str, Any] = {
        "schema_version": 1,
        "model": "claude-sonnet-5-5",
        "totals": AgentTotals(
            tokens=AgentTokens(input=82, output=19038, cache_creation=148841, cache_read=4469981)
        ),
        "stages": {
            "leitura": stage(4, 247, 61359),
            "cadastro": stage(20, 5788, 43436),
            "alcance": stage(18, 3774, 8554),
            "varredura": stage(28, 3009, 13589),
            "triagem": stage(10, 4970, 20062),
            "outro": stage(2, 1250, 1841),
        },
    }
    base.update(changes)
    return AgentMetrics(**base)


def measured_view(**changes: Any) -> PanelView:
    """Visão do cenário feliz, com `metrics.json` e `agent-metrics.json`."""
    base: dict[str, Any] = {"metrics": run_metrics(), "agent_metrics": agent_metrics()}
    base.update(changes)
    return view(**base)
