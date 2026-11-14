"""Medição de uma regra de varredura ativa do ZAP em uma varredura (ADR 0031). Módulo puro.

Só números e identificadores: o id da regra, o nome que o ZAP dá a ela, quanto tempo gastou,
quantos pedidos enviou e quantos alertas levantou. Nada do alvo entra aqui.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

from pydantic import Field

from harness_dast.domain.api_schema import ApiModel

RuleState = Literal["completed", "skipped", "interrupted", "pending", "unknown"]
"""Estado final da regra: `completed` (concluída), `skipped` (o ZAP a pulou), `interrupted`
(ainda rodava quando a varredura terminou ou foi parada), `pending` (nunca começou) ou
`unknown` (texto de estado que a CLI não conhece)."""

MAX_RULE_NAME: Final = 120
MAX_REASON: Final = 300


class RuleStat(ApiModel):
    """O que uma regra do ZAP fez em UMA varredura.

    Attributes:
        plugin_id: Identificador da regra no ZAP.
        name: Nome da regra, como o ZAP a chama.
        state: Estado final.
        time_ms: Tempo gasto em milissegundos, ou `None` se o ZAP não informou.
        requests: Pedidos que a regra enviou.
        alerts: Alertas que a regra levantou.
        skip_reason: Motivo do pulo, em código (`max_rule_time`, `other`), só se `skipped`.
    """

    plugin_id: int = Field(ge=0)
    name: str = Field(max_length=MAX_RULE_NAME)
    state: RuleState
    time_ms: int | None = Field(default=None, ge=0)
    requests: int = Field(default=0, ge=0)
    alerts: int = Field(default=0, ge=0)
    skip_reason: str | None = None


class OperationRules(ApiModel):
    """As regras de UMA varredura (uma operação), ou o motivo de não haver o dado.

    Attributes:
        operation_id: Operação varrida.
        scan_id: Identificador da varredura no ZAP.
        rules: Medição de cada regra; vazio se a coleta falhou.
        unavailable_reason: Por que a medição não existe (a coleta falhou), ou `None`.
    """

    operation_id: str
    scan_id: str
    rules: tuple[RuleStat, ...] = ()
    unavailable_reason: str | None = Field(default=None, max_length=MAX_REASON)


class RuleStatsFile(ApiModel):
    """Conteúdo de `rule-stats.json`: o dado bruto por regra, por operação, que o `scan` coletou.

    Attributes:
        schema_version: Versão do formato (1).
        run_id: Execução.
        zap_version: Versão do ZAP, quando o `scan` a conheceu.
        operations: Uma entrada por varredura que chegou a começar, na ordem.
    """

    schema_version: int = 1
    run_id: str
    zap_version: str | None = Field(default=None, max_length=40)
    operations: tuple[OperationRules, ...] = ()


class RuleTotal(ApiModel):
    """Soma de uma regra em todas as varreduras da execução.

    Attributes:
        plugin_id: Identificador da regra no ZAP.
        name: Nome da regra.
        time_ms: Tempo somado (só das varreduras em que o ZAP informou o tempo).
        requests: Pedidos somados.
        alerts: Alertas somados.
        operations: Em quantas varreduras (operações) a regra apareceu.
        completed: Quantas vezes terminou.
        skipped: Quantas vezes foi pulada.
        interrupted: Quantas vezes foi interrompida.
        pending: Quantas vezes nem começou.
        unknown: Quantas vezes veio com estado desconhecido.
    """

    plugin_id: int
    name: str
    time_ms: int
    requests: int
    alerts: int
    operations: int
    completed: int
    skipped: int
    interrupted: int
    pending: int
    unknown: int


@dataclass
class _Sum:
    name: str
    time_ms: int = 0
    requests: int = 0
    alerts: int = 0
    states: Counter[str] = field(default_factory=Counter)

    def total(self, plugin_id: int) -> RuleTotal:
        return RuleTotal(
            plugin_id=plugin_id,
            name=self.name,
            time_ms=self.time_ms,
            requests=self.requests,
            alerts=self.alerts,
            operations=self.states.total(),
            completed=self.states["completed"],
            skipped=self.states["skipped"],
            interrupted=self.states["interrupted"],
            pending=self.states["pending"],
            unknown=self.states["unknown"],
        )


def total_rules(per_operation: Sequence[Sequence[RuleStat]]) -> tuple[RuleTotal, ...]:
    """Soma as regras de todas as varreduras, da mais lenta para a mais rápida.

    Empate no tempo desempata por `plugin_id`, para a saída ser estável.
    """
    sums: dict[int, _Sum] = {}
    for rules in per_operation:
        for rule in rules:
            row = sums.setdefault(rule.plugin_id, _Sum(name=rule.name))
            row.time_ms += rule.time_ms or 0
            row.requests += rule.requests
            row.alerts += rule.alerts
            row.states[rule.state] += 1
    ordered = sorted(sums.items(), key=lambda item: (-item[1].time_ms, item[0]))
    return tuple(row.total(plugin_id) for plugin_id, row in ordered)
