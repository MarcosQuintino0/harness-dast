"""Criterios (c) achados contra o gabarito (modo vulneravel) e (d) falsos alarmes (modo seguro)."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.runner.models import Case, Check, Component, Flaw, Matcher

WEIGHT = 25.0
ACHADA, PARCIAL, NAO_ACHADA = "achada", "em parte", "nao achada"
CREDIT = {ACHADA: 1.0, PARCIAL: 0.5, NAO_ACHADA: 0.0}
FALSE_ALARM_STEP = 0.25


def read_findings(trace: Path) -> list[dict[str, Any]]:
    """Achados de todas as execucoes (do ZAP e do estagio authz), sem repetir fingerprint."""
    seen: dict[str, dict[str, Any]] = {}
    for file in sorted((trace / "runs").glob("*/findings.json")):
        data = json.loads(file.read_text(encoding="utf-8"))
        authz = data.get("authz") or {}
        signals = data.get("proxy_signals") or {}
        negative = data.get("negative") or {}
        for finding in [
            *data.get("findings", []),
            *authz.get("findings", []),
            *signals.get("findings", []),
            *negative.get("findings", []),
        ]:
            seen.setdefault(str(finding.get("fingerprint", id(finding))), finding)
    return list(seen.values())


def matches(finding: dict[str, Any], matcher: Matcher) -> bool:
    """Todas as condicoes informadas do `matcher` valem para o achado."""
    title = str(finding.get("title", "")).lower()
    if matcher.titles and not any(item.lower() in title for item in matcher.titles):
        return False
    path = str(finding.get("path_template", ""))
    if matcher.path_contains and matcher.path_contains not in path:
        return False
    parameter = str(finding.get("parameter", "")).lower()
    if matcher.parameter and matcher.parameter.lower() != parameter:
        return False
    method = str(finding.get("method", "")).upper()
    if matcher.method and matcher.method.upper() != method:
        return False
    return all(
        expected is None or expected == finding.get(field)
        for field, expected in (
            ("technique", matcher.technique),
            ("category", matcher.category),
            ("operation_id", matcher.operation_id),
        )
    )


def flaw_status(flaw: Flaw, findings: list[dict[str, Any]]) -> str:
    """`achada`, `em parte` ou `nao achada`."""
    if any(
        matches(item, matcher)
        for item in findings
        for matcher in ((flaw.match,) if flaw.match else ()) + flaw.match_any
    ):
        return ACHADA
    if flaw.partial and any(matches(item, flaw.partial) for item in findings):
        return PARCIAL
    return NAO_ACHADA


@dataclass(frozen=True)
class FlawResult:
    """Situacao de uma falha plantada."""

    flaw: Flaw
    status: str


def evaluate_flaws(case: Case, findings: list[dict[str, Any]]) -> list[FlawResult]:
    """Situacao de cada falha do gabarito."""
    return [FlawResult(flaw, flaw_status(flaw, findings)) for flaw in case.flaws]


def found_component(case: Case, findings: list[dict[str, Any]]) -> Component:
    """(c) Modo vulneravel: credito ponderado das falhas detectaveis; o resto so no relatorio."""
    results = evaluate_flaws(case, findings)
    scored = [item for item in results if item.flaw.detectable]
    total = sum(item.flaw.weight for item in scored)
    earned = sum(item.flaw.weight * CREDIT[item.status] for item in scored)
    checks = tuple(
        Check(
            id=f"flaw_{item.flaw.id}",
            title=f"{item.flaw.id}: {item.flaw.title}",
            passed=item.status == ACHADA,
            detail=item.status,
        )
        for item in scored
    )
    notes = tuple(
        f"{item.flaw.id} ({item.flaw.title}): nao detectavel por desenho; "
        f"{'o agente a reportou' if item.status != NAO_ACHADA else 'nao reportada'}; fora da nota"
        for item in results
        if not item.flaw.detectable
    )
    return Component(
        id="found",
        title="(c) Achados contra o gabarito (modo vulneravel)",
        weight=WEIGHT,
        score=earned / total if total else None,
        checks=checks,
        notes=notes,
    )


def false_alarms(case: Case, findings: list[dict[str, Any]]) -> list[str]:
    """Achados de classe plantada ou de severidade alta, que no modo seguro sao falso alarme."""
    matchers = [
        m
        for flaw in case.flaws
        for m in (flaw.match, flaw.partial, *flaw.match_any)
        if m is not None
    ]
    alarms: list[str] = []
    for item in findings:
        high = str(item.get("proposed_severity", "")) == "high"
        planted = any(matches(item, matcher) for matcher in matchers)
        if high or planted:
            alarms.append(
                f"{item.get('title')} em {item.get('method')} {item.get('path_template')}"
            )
    return alarms


def has_report(trace: Path) -> bool:
    """Diz se alguma execucao gravou `findings.json` (houve varredura e relatorio)."""
    return any((trace / "runs").glob("*/findings.json"))


def alarm_component(
    case: Case, findings: list[dict[str, Any]], *, reported: bool = True
) -> Component:
    """(d) Modo seguro: 1 sem falso alarme; menos 0,25 por falso alarme, no minimo 0.

    Sem relatorio (`reported` falso) o criterio nao se aplica: nada foi varrido, e "nenhum
    falso alarme" nao pode valer nota cheia.
    """
    if not reported:
        return Component(
            id="alarms",
            title="(d) Falsos alarmes (modo seguro)",
            weight=WEIGHT,
            score=None,
            checks=(
                Check(
                    id="no_false_alarms",
                    title="Nenhum achado alto nem de classe plantada no modo seguro",
                    passed=False,
                    detail="nao se aplica: nenhuma execucao gerou findings.json",
                ),
            ),
        )
    alarms = false_alarms(case, findings)
    return Component(
        id="alarms",
        title="(d) Falsos alarmes (modo seguro)",
        weight=WEIGHT,
        score=max(0.0, 1.0 - FALSE_ALARM_STEP * len(alarms)),
        checks=(
            Check(
                id="no_false_alarms",
                title="Nenhum achado alto nem de classe plantada no modo seguro",
                passed=not alarms,
                detail=f"{len(alarms)}: {alarms[:5]}" if alarms else "nenhum",
            ),
        ),
    )
