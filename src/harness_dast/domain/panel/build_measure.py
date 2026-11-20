"""Medição do painel: tempo por regra e função (`metrics.json`) e tokens do agente. Módulo puro.

Os tokens vêm de `agent-metrics.json`, que fala em etapas do AGENTE (leitura, cadastro, alcance,
varredura, triagem, outro), e o painel fala em etapas da CLI. A correspondência é fixa e simples:
leitura e cadastro são o trabalho da conferência; alcance, varredura e triagem (os achados) têm
a etapa própria; o teste entre contas não tem trabalho de agente separado; o que sobra (`outro`
e etapa que não conhecemos) vai para `other`. Etapa sem token no arquivo não aparece, e arquivo
ausente deixa tudo `None`: traço e "não medido", nunca zero.
"""

from collections.abc import Sequence
from typing import Final

from harness_dast.domain.agent_metrics import AgentMetrics
from harness_dast.domain.panel.model import PanelMeasurements, PanelStage, PanelTokens
from harness_dast.domain.run_metrics import RunMetrics

OTHER_TOKENS: Final = "other"
"""Chave, em `tokens_by_stage`, do trabalho do agente que não é de nenhuma etapa da CLI."""

_AGENT_TO_CLI: Final[dict[str, str]] = {
    "leitura": "preflight",
    "cadastro": "preflight",
    "alcance": "probe",
    "varredura": "scan",
    "triagem": "report",
}


def _stage_tokens(agent: AgentMetrics) -> dict[str, int] | None:
    totals: dict[str, int] = {}
    for name, stage in agent.stages.items():
        if stage.tokens is None:
            continue
        key = _AGENT_TO_CLI.get(name, OTHER_TOKENS)
        totals[key] = totals.get(key, 0) + stage.tokens.counted
    return totals or None


def build_measurements(metrics: RunMetrics | None, agent: AgentMetrics | None) -> PanelMeasurements:
    """Junta o `metrics.json` (tempo) e o `agent-metrics.json` (tokens); cada um pode faltar."""
    tokens = agent.totals.tokens if agent and agent.totals else None
    by_stage = _stage_tokens(agent) if agent else None
    base = PanelMeasurements()
    if metrics is not None:
        base = PanelMeasurements(
            metrics_available=True,
            operations=metrics.operations,
            rules=metrics.rules.totals,
            rules_measured=metrics.rules.operations_measured,
            rules_unavailable=metrics.rules.operations_unavailable,
            gaps=metrics.traffic.gaps,
            disabled_rules=metrics.disabled_rules,
        )
    if agent is None:
        return base
    return base.model_copy(
        update={
            "tokens_total": tokens.counted if tokens else None,
            "tokens_by_stage": by_stage,
            "tokens_breakdown": PanelTokens(
                input=tokens.input,
                output=tokens.output,
                cache_written=tokens.cache_creation,
                cache_read=tokens.cache_read,
            )
            if tokens
            else None,
            "agent_model": agent.model,
        }
    )


def with_stage_tokens(
    stages: Sequence[PanelStage], by_stage: dict[str, int] | None
) -> tuple[PanelStage, ...]:
    """Põe em cada etapa os tokens do agente, quando o arquivo os trouxe (senão, `None`)."""
    if by_stage is None:
        return tuple(stages)
    return tuple(stage.model_copy(update={"tokens": by_stage.get(stage.key)}) for stage in stages)
