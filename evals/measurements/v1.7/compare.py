"""Compara registros redigidos V1.7; não declara detecção nem segurança equivalentes."""

import json
import sys
from collections import Counter
from pathlib import Path


def _work(record: dict) -> tuple[Counter, list[str]]:
    issues = []
    scan = record.get("scan") or {}
    stats = record.get("rule_stats") or {}
    entries = scan.get("entries") or []
    operations = stats.get("operations") or []
    if scan.get("status") != "completed" or not entries or scan.get("skipped"):
        issues.append("scan ausente, incompleto ou com operações puladas")
    for entry in entries:
        if entry.get("outcome") != "completed" or entry.get("truncated"):
            issues.append("operação interrompida ou truncada")
    expected = Counter(entry.get("operation_id") for entry in entries)
    observed = Counter(item.get("operation_id") for item in operations)
    if expected != observed:
        issues.append("estatísticas por operação ausentes ou duplicadas")
    work: Counter = Counter()
    for operation in operations:
        rules = operation.get("rules") or []
        if operation.get("unavailable_reason") or not rules:
            issues.append("regras indisponíveis")
        for rule in rules:
            if rule.get("state") != "completed" or rule.get("time_ms") is None:
                issues.append("regra não concluída ou sem tempo")
            work[(operation.get("operation_id"), rule.get("plugin_id"), rule.get("state"))] += 1
    return work, issues


def compare(a: dict, b: dict) -> dict:
    """Compara regras, política e contas observadas; sem dados retorna inconclusivo."""
    work_a, issues_a = _work(a)
    work_b, issues_b = _work(b)
    issues = issues_a + issues_b
    scan_a, scan_b = a.get("scan") or {}, b.get("scan") or {}
    if scan_a.get("policy") is None or scan_a.get("policy") != scan_b.get("policy"):
        issues.append("política ausente ou diferente")
    if work_a != work_b:
        issues.append("operações/regras executadas divergem")

    def accounts(record: dict) -> Counter:
        return Counter(
            (row.get("operation_id"), row.get("account"), row.get("method"), row.get("route"))
            for row in record.get("accounts", [])
            if row.get("phase") == "decision" and row.get("decision") == "allowed"
        )

    accounts_a, accounts_b = accounts(a), accounts(b)
    if not accounts_a or not accounts_b:
        issues.append("contas observadas ausentes")
    elif set(accounts_a) != set(accounts_b):
        issues.append("combinações operação/conta/método/rota divergem")
    issues.append(
        "pontos de injeção, controles, autorização, limites e atribuição requerem aferição"
    )
    return {"status": "inconclusivo", "issues": sorted(set(issues))}


if __name__ == "__main__":
    first, second = (json.loads(Path(arg).read_text(encoding="utf-8")) for arg in sys.argv[1:3])
    sys.stdout.write(json.dumps(compare(first, second), ensure_ascii=False, indent=2) + "\n")
