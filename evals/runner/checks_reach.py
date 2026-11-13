"""Criterio (b): alcancabilidade do `probe`."""

import json
from dataclasses import dataclass
from pathlib import Path

from evals.runner.models import Check, Component

WEIGHT = 25.0
GOAL = 0.9
BY_DESIGN = ("skipped_scope", "skipped_denied", "skipped_destructive")
FULL_PROBE_SHARE = 0.5


@dataclass(frozen=True)
class ProbeView:
    """Numeros de um `probe.json` de envio real."""

    run: str
    finished_at: str
    total: int
    sent: int
    successes: int
    by_design: int

    @property
    def effective(self) -> float:
        """Sucessos sobre as operacoes que podiam ser alcancadas (sem as puladas por desenho)."""
        reachable = max(1, self.total - self.by_design)
        return self.successes / reachable


def read_probes(trace: Path) -> list[ProbeView]:
    """Todos os `probe.json` de envio real da rodada."""
    views: list[ProbeView] = []
    for file in sorted((trace / "runs").glob("*/probe.json")):
        data = json.loads(file.read_text(encoding="utf-8"))
        if data.get("dry_run"):
            continue
        summary = data.get("summary", {})
        outcomes = summary.get("by_outcome", {})
        views.append(
            ProbeView(
                run=file.parent.name,
                finished_at=str(data.get("finished_at", "")),
                total=int(summary.get("operations_total", 0)),
                sent=int(summary.get("operations_sent", 0)),
                successes=int(summary.get("successes", 0)),
                by_design=sum(int(outcomes.get(name, 0)) for name in BY_DESIGN),
            )
        )
    return views


def pick(views: list[ProbeView]) -> ProbeView | None:
    """O `probe` mais recente que tentou pelo menos metade do alcancavel; senao o melhor."""
    if not views:
        return None
    full = [
        view
        for view in views
        if view.sent >= FULL_PROBE_SHARE * max(1, view.total - view.by_design)
    ]
    if full:
        return max(full, key=lambda view: view.finished_at)
    return max(views, key=lambda view: view.effective)


def reach_component(trace: Path) -> Component:
    """Nota de alcancabilidade: `min(1, efetiva / 0,9)`; sem probe real, zero."""
    chosen = pick(read_probes(trace))
    if chosen is None:
        return Component(
            id="reach",
            title="(b) Alcancabilidade do probe",
            weight=WEIGHT,
            score=0.0,
            checks=(Check(id="probe_ran", title="Houve um probe de envio real", passed=False),),
        )
    score = min(1.0, chosen.effective / GOAL)
    detail = (
        f"execucao {chosen.run}: {chosen.successes} sucessos de {chosen.total - chosen.by_design} "
        f"operacoes alcancaveis ({chosen.by_design} puladas por desenho); "
        f"efetiva {chosen.effective:.2f}"
    )
    return Component(
        id="reach",
        title="(b) Alcancabilidade do probe",
        weight=WEIGHT,
        score=score,
        checks=(
            Check(
                id="reach_goal",
                title=f"Meta de {GOAL:.0%}",
                passed=chosen.effective >= GOAL,
                detail=detail,
            ),
        ),
    )
