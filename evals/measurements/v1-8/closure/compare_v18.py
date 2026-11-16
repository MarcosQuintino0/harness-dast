"""Compara evidências sanitizadas de T4; divergências exigem revisão, não aprovação automática."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _counts(record: dict[str, Any]) -> dict[str, Counter[str]]:
    scan = record.get("scan") or {}
    stats = record.get("rule_stats") or {}
    operations = Counter(
        json.dumps(
            [
                e.get("operation_id"),
                e.get("method"),
                e.get("path"),
                e.get("outcome"),
                e.get("truncated"),
            ],
            ensure_ascii=False,
        )
        for e in scan.get("entries", [])
    )
    skipped = Counter(
        json.dumps(
            [e.get("operation_id"), e.get("method"), e.get("path"), e.get("reason")],
            ensure_ascii=False,
        )
        for e in scan.get("skipped", [])
    )
    rules = Counter()
    requests = Counter()
    alerts = Counter()
    for operation in stats.get("operations", []):
        for rule in operation.get("rules", []):
            if rule.get("plugin_id") == 40026:
                continue
            key = json.dumps(
                [operation.get("operation_id"), rule.get("plugin_id"), rule.get("state")],
                ensure_ascii=False,
            )
            rules[key] += 1
            if isinstance(rule.get("requests"), int):
                requests[key] += rule["requests"]
            else:
                requests[key + " MISSING"] += 1
            if isinstance(rule.get("alerts"), int):
                alerts[key] += rule["alerts"]
            else:
                alerts[key + " MISSING"] += 1
    findings = Counter(
        json.dumps(
            [f.get("title"), f.get("method"), f.get("path_template"), f.get("attribution")],
            ensure_ascii=False,
        )
        for f in record.get("findings", [])
    )
    return {
        "operations": operations,
        "skipped": skipped,
        "rules": rules,
        "requests": requests,
        "alerts": alerts,
        "findings": findings,
    }


def compare(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Preserva contagens e diferenças; nunca transforma ausência ou diferença em aceite."""
    counts_a, counts_b = _counts(a), _counts(b)
    result = {}
    for category in counts_a:
        keys = sorted(set(counts_a[category]) | set(counts_b[category]))
        result[category] = [
            {
                "key": (key if key.endswith(" MISSING") else json.loads(key)),
                "a": counts_a[category][key],
                "b": counts_b[category][key],
            }
            for key in keys
            if counts_a[category][key] != counts_b[category][key]
        ]
    gaps = []
    for name, record in (("A", a), ("B", b)):
        if record.get("exit_code") != 0 or (record.get("scan") or {}).get("status") != "completed":
            gaps.append(f"{name}: execução ou scan incompleto")
        if (
            not counts_a["operations"]
            or not counts_b["operations"]
            or not counts_a["rules"]
            or not counts_b["rules"]
        ):
            gaps.append("operações ou regras ausentes")
    gaps.append(
        "Origens ZAP/authz/negative e controles exigem evidência separada; atribuição não é origem"
    )
    return {
        "status": "revisao_necessaria",
        "gaps": sorted(set(gaps)),
        "differences": result,
        "counts": {
            name: {"a": dict(counts_a[name]), "b": dict(counts_b[name])} for name in counts_a
        },
        "limitation": "Contagens variam; investigar diferenças antes de decidir.",
    }


def compare_origins(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Compara achados extra?dos das tr?s fontes sem usar atribui??o como origem."""
    output: dict[str, Any] = {}
    for origin in ("zap", "authz", "negative"):
        source_a = a.get("sources", {}).get(origin, {})
        source_b = b.get("sources", {}).get(origin, {})
        counts = []
        for source in (source_a, source_b):
            counts.append(
                Counter(
                    json.dumps(row, ensure_ascii=False, sort_keys=True)
                    for row in source.get("findings", [])
                    if row.get("plugin_id") != 40026
                )
            )
        keys = sorted(set(counts[0]) | set(counts[1]))
        output[origin] = {
            "run_id_a": a.get("run_id"),
            "run_id_b": b.get("run_id"),
            "source_a": {key: source_a.get(key) for key in ("path", "sha256")},
            "source_b": {key: source_b.get(key) for key in ("path", "sha256")},
            "status_a": source_a.get("status", "ausente"),
            "status_b": source_b.get("status", "ausente"),
            "counts": [
                {"finding": json.loads(key), "a": counts[0][key], "b": counts[1][key]}
                for key in keys
            ],
        }
    return output


def main() -> None:
    """Lê dois registros sanitizados e grava comparação em arquivo novo."""
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--origins-a", type=Path)
    parser.add_argument("--origins-b", type=Path)
    args = parser.parse_args()
    raw_a, raw_b = args.baseline.read_bytes(), args.candidate.read_bytes()
    record_a, record_b = json.loads(raw_a), json.loads(raw_b)
    result = compare(record_a, record_b)
    if bool(args.origins_a) != bool(args.origins_b):
        parser.error("Informe as duas fontes de origem")
    if args.origins_a and args.origins_b:
        origins_a = json.loads(args.origins_a.read_text(encoding="utf-8"))
        origins_b = json.loads(args.origins_b.read_text(encoding="utf-8"))
        if origins_a.get("run_id") != (record_a.get("manifest") or {}).get(
            "run_id"
        ) or origins_b.get("run_id") != (record_b.get("manifest") or {}).get("run_id"):
            parser.error("Matriz de origem n?o corresponde ? execu??o")
        result["origin_comparison"] = compare_origins(origins_a, origins_b)
    result["source_sha256"] = {
        "a": hashlib.sha256(raw_a).hexdigest(),
        "b": hashlib.sha256(raw_b).hexdigest(),
    }
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, ensure_ascii=False)
        output.write("\n")


if __name__ == "__main__":
    main()
