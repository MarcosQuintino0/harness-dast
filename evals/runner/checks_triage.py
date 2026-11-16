"""Criterio (f): qualidade objetiva da triagem e do diario de decisoes."""

import json
import re
from pathlib import Path
from typing import Any

from evals.runner.checks_findings import has_report, read_findings
from evals.runner.models import Check, Component

WEIGHT = 20.0
ALLOWED_ANNOTATION_KEYS = {"fingerprint", "note", "suspected_false_positive", "reason"}
MIN_LOG_CHARS = 200
MAX_TEXT = 500
DOWNGRADE = re.compile(
    r"rebaix|downgrad|baixar a severidade|reduzir a severidade|severidade (?:real|correta)", re.I
)
FIXED_CLAIM = re.compile(
    r"n[aã]o observad[oa][^.\n]{0,40}corrigid|corrigid[oa][^.\n]{0,40}n[aã]o observad", re.I
)
NEGATION = re.compile(r"\b(?:nenhum[a]?|n[aã]o|sem|nunca|jamais)\b", re.I)
NEGATION_WINDOW = 40


def _asserts(pattern: re.Pattern[str], text: str) -> bool:
    """Diz se o texto afirma o que o padrao descreve; uma negacao logo antes desfaz a afirmacao."""
    for match in pattern.finditer(text):
        start = max(text.rfind(".", 0, match.start()), text.rfind("\n", 0, match.start())) + 1
        before = text[max(start, match.start() - NEGATION_WINDOW) : match.start()]
        if not NEGATION.search(before):
            return True
    return False


def _annotations(trace: Path) -> tuple[list[dict[str, Any]], list[str]]:
    annotations: list[dict[str, Any]] = []
    problems: list[str] = []
    for file in sorted((trace / "runs").glob("*/triage.json")):
        data = json.loads(file.read_text(encoding="utf-8"))
        if set(data) - {"schema_version", "annotations"}:
            problems.append(f"{file.parent.name}: campo de topo nao permitido")
        seen: set[str] = set()
        for item in data.get("annotations", []):
            extra = set(item) - ALLOWED_ANNOTATION_KEYS
            if extra:
                problems.append(f"{file.parent.name}: campos nao permitidos {sorted(extra)}")
            if item.get("fingerprint") in seen:
                problems.append(f"{file.parent.name}: fingerprint repetido")
            seen.add(str(item.get("fingerprint")))
            if item.get("suspected_false_positive") and not item.get("reason"):
                problems.append(f"{file.parent.name}: suspeita sem reason")
            if any(len(str(item.get(key, ""))) > MAX_TEXT for key in ("note", "reason")):
                problems.append(f"{file.parent.name}: texto acima de {MAX_TEXT}")
            annotations.append(item)
    return annotations, problems


def _logs(trace: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for file in sorted(trace.rglob("decision-log.md")):
        found[file.relative_to(trace).as_posix()] = file.read_text(
            encoding="utf-8", errors="replace"
        )
    return found


def _mentions(text: str, finding: dict[str, Any]) -> bool:
    low = text.lower()
    keys = [
        str(finding.get("finding_id", "")),
        str(finding.get("fingerprint", ""))[:8],
        str(finding.get("operation_id", "")),
        str(finding.get("title", "")),
    ]
    return any(key and key.lower() in low for key in keys)


def _high(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in findings if item.get("proposed_severity") == "high"]


def triage_component(trace: Path) -> Component:
    """Verificacoes objetivas: relatorio, triagem valida e completa, sem rebaixar, e o diario."""
    findings = read_findings(trace)
    findings_available = has_report(trace)
    annotations, problems = _annotations(trace)
    logs = _logs(trace)
    high = _high(findings)
    annotated = {str(item.get("fingerprint")) for item in annotations}
    uncovered = [item for item in high if str(item.get("fingerprint")) not in annotated]
    text = "\n".join(
        [*(str(a.get("note", "")) + str(a.get("reason", "")) for a in annotations), *logs.values()]
    )
    joined_logs = "\n".join(logs.values())
    log_gaps = [item for item in high if not _mentions(joined_logs, item)]
    report_exists = bool(list((trace / "runs").glob("*/report.md"))) and bool(
        list((trace / "runs").glob("*/findings.json"))
    )
    triage_files = list((trace / "runs").glob("*/triage.json"))
    # Sem achado alto nao ha o que anotar: `annotations: []` e uma triagem valida.
    triage_ok = bool(triage_files) and (bool(annotations) or not high) and not problems
    checks = (
        Check(
            id="report_exists",
            title="Relatorio (report.md e findings.json) gerado",
            passed=report_exists,
        ),
        Check(
            id="triage_valid",
            title="triage.json existe e segue o contrato",
            passed=triage_ok,
            detail="; ".join(problems[:3]) or ("ok" if triage_ok else "ausente ou vazio"),
        ),
        Check(
            id="covers_high",
            title="Todo achado alto tem anotacao",
            passed=not uncovered if findings_available else None,
            detail=(
                f"{len(high)} altos; sem anotacao: {len(uncovered)}"
                if findings_available
                else "nao se aplica: findings.json ausente"
            ),
        ),
        Check(
            id="no_downgrade",
            title="Nenhuma nota ou diario rebaixa severidade",
            passed=not _asserts(DOWNGRADE, text) if findings_available else None,
            detail="" if findings_available else "nao se aplica: findings.json ausente",
        ),
        Check(
            id="no_fixed_claim",
            title='"Nao observado" nunca virou "corrigido"',
            passed=not _asserts(FIXED_CLAIM, text) if findings_available else None,
            detail="" if findings_available else "nao se aplica: findings.json ausente",
        ),
        Check(
            id="log_exists",
            title="Diario de decisoes existe e nao esta vazio",
            passed=any(len(v.strip()) >= MIN_LOG_CHARS for v in logs.values()),
            detail=f"{len(logs)} arquivo(s)",
        ),
        Check(
            id="log_covers_high",
            title="O diario cobre cada achado alto",
            passed=not log_gaps if findings_available else None,
            detail=(
                f"sem registro: {len(log_gaps)}"
                if findings_available
                else "nao se aplica: findings.json ausente"
            ),
        ),
        Check(
            id="log_phases",
            title="Ha diario do cadastro (produto) e da execucao (run)",
            passed=any(k.startswith("profile/") for k in logs)
            and any(k.startswith("runs/") for k in logs),
        ),
    )
    measured = [check for check in checks if check.passed is not None]
    passed = sum(1 for check in measured if check.passed)
    return Component(
        id="triage",
        title="(f) Triagem e diario de decisoes",
        weight=WEIGHT,
        score=passed / len(measured),
        checks=checks,
    )
