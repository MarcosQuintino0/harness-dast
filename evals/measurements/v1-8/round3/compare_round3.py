"""Compara T4 preservando diferenças e fontes; não decide promoção automaticamente."""

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
CLOSURE = HERE.parent / "closure"


def module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Nao foi possivel carregar {path}")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


base = module("compare_v18", CLOSURE / "compare_v18.py")
detail = module("derive_findings_v18", CLOSURE / "derive_findings_v18.py")


def read(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def dom(record: dict[str, Any]) -> list[tuple[str, str, str, Any]]:
    return sorted(
        (
            str(op.get("operation_id")),
            str(rule.get("state")),
            str(rule.get("skip_reason")),
            rule.get("requests"),
        )
        for op in (record.get("rule_stats") or {}).get("operations", [])
        for rule in op.get("rules", [])
        if str(rule.get("plugin_id")) == "40026"
    )


def diagnostic(record: dict[str, Any]) -> dict[str, Any]:
    """Apresenta contexto e lacunas sem inferir identidade ou igualdade de campos ausentes."""
    scan = record.get("scan") or {}
    stats = record.get("rule_stats") or {}
    rules = [
        (operation.get("operation_id"), rule)
        for operation in stats.get("operations", [])
        for rule in operation.get("rules", [])
    ]
    missing_counts = [
        {"operation_id": op, "plugin_id": rule.get("plugin_id"), "field": field}
        for op, rule in rules
        if str(rule.get("plugin_id")) != "40026"
        for field in ("requests", "alerts")
        if type(rule.get(field)) is not int
    ]
    skipped_reasons = Counter(
        json.dumps(
            [op, rule.get("plugin_id"), rule.get("state"), rule.get("skip_reason")],
            ensure_ascii=False,
        )
        for op, rule in rules
        if str(rule.get("plugin_id")) != "40026" and rule.get("state") != "completed"
    )
    probe = [
        {
            key: row.get(key)
            for key in (
                "operation_id",
                "method",
                "path",
                "outcome",
                "status",
                "account",
                "blocked_dependencies",
            )
        }
        for row in (record.get("probe") or [])
    ]
    accounts = Counter(
        json.dumps(
            [
                row.get(key)
                for key in ("phase", "route", "decision", "operation_id", "account", "method")
            ],
            ensure_ascii=False,
        )
        for row in (record.get("accounts") or [])
    )
    audit_counts = Counter(
        json.dumps([row.get("decision"), row.get("reason")], ensure_ascii=False)
        for row in (record.get("proxy_audit") or [])
    )
    operation_ids = [str(op.get("operation_id")) for op in stats.get("operations", [])]
    dom_ids = [entry[0] for entry in dom(record)]
    scanned_ids = [str(entry.get("operation_id")) for entry in scan.get("entries", [])]
    return {
        "context": {
            "profile": record.get("profile"),
            "policy": scan.get("policy"),
            "limits": scan.get("limits"),
            "planned": scan.get("planned"),
            "zap_version": stats.get("zap_version"),
            "probe": probe if isinstance(record.get("probe"), list) else None,
        },
        "proxy_audit_decision_reason_counts": (
            dict(audit_counts) if isinstance(record.get("proxy_audit"), list) else None
        ),
        "authentication_presence": record.get("auth_on_scanner"),
        "csrf": record.get("csrf"),
        "account_event_counts": dict(accounts)
        if isinstance(record.get("accounts"), list)
        else None,
        "rule_data_available": bool(rules),
        "missing_rule_counts": missing_counts,
        "non_dom_noncompleted_rules": dict(skipped_reasons),
        "dom_covers_each_stats_operation": bool(operation_ids)
        and Counter(operation_ids) == Counter(dom_ids) == Counter(scanned_ids),
        "counts": {
            "operations": len(scan.get("entries", [])),
            "skipped": len(scan.get("skipped", [])),
            "rule_pairs": len(rules),
            "findings": len(record.get("findings", [])),
        },
    }


def seconds(record: dict[str, Any]) -> float:
    scan = record["scan"]
    return (
        datetime.fromisoformat(scan["finished_at"].replace("Z", "+00:00"))
        - datetime.fromisoformat(scan["started_at"].replace("Z", "+00:00"))
    ).total_seconds()


def detail_origins(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for origin in ("zap", "authz", "negative"):
        ma, aa = detail.extract(a, origin)
        mb, bb = detail.extract(b, origin)
        attributes_a = detail.tally([x["attributes"] for x in aa])
        attributes_b = detail.tally([x["attributes"] for x in bb])
        fp_a = detail.tally([x["fingerprint"] for x in aa])
        fp_b = detail.tally([x["fingerprint"] for x in bb])
        result[origin] = {
            "source_a": ma,
            "source_b": mb,
            "attributes": detail.paired(attributes_a, attributes_b),
            "fingerprints": detail.paired(fp_a, fp_b),
            "missing_fingerprints": {
                "a": sum(x["fingerprint"] is None for x in aa),
                "b": sum(x["fingerprint"] is None for x in bb),
            },
            "missing_fields": {
                field: {
                    "a": sum(row["attributes"][field]["state"] != "present" for row in aa),
                    "b": sum(row["attributes"][field]["state"] != "present" for row in bb),
                }
                for field in detail.FIELDS
            },
        }
    return result


def compare(
    a_path: Path, b_path: Path, ao_path: Path | None = None, bo_path: Path | None = None
) -> dict[str, Any]:
    a, ash = read(a_path)
    b, bsh = read(b_path)
    result: dict[str, Any] = base.compare(a, b)
    diag_a, diag_b = diagnostic(a), diagnostic(b)
    result["diagnostics"] = {
        "a": diag_a,
        "b": diag_b,
        "context_equal": {
            key: diag_a["context"][key] == diag_b["context"][key]
            if diag_a["context"][key] is not None and diag_b["context"][key] is not None
            else None
            for key in diag_a["context"]
        },
        "non_dom_noncompleted_rules_equal": (
            diag_a["non_dom_noncompleted_rules"] == diag_b["non_dom_noncompleted_rules"]
            if diag_a["rule_data_available"] and diag_b["rule_data_available"]
            else None
        ),
    }
    result.update(
        {
            "sources": {
                "a": {"path": str(a_path), "sha256": ash},
                "b": {"path": str(b_path), "sha256": bsh},
            },
            "run_ids": {"a": a["manifest"]["run_id"], "b": b["manifest"]["run_id"]},
            "scan_seconds": {"a": seconds(a), "b": seconds(b)},
            "dom_40026": {
                "a": dom(a),
                "b": dom(b),
                "historical_exclusion_valid": diag_a["dom_covers_each_stats_operation"]
                and diag_b["dom_covers_each_stats_operation"]
                and bool(dom(a))
                and dom(a) == dom(b)
                and all(x[1:] == ("skipped", "other", 0) for x in dom(a)),
            },
        }
    )
    if ao_path and bo_path:
        ao, aosh = read(ao_path)
        bo, bosh = read(bo_path)
        if ao["run_id"] != result["run_ids"]["a"] or bo["run_id"] != result["run_ids"]["b"]:
            raise ValueError("origem não corresponde ao run")
        result["origin_files"] = {
            "a": {"path": str(ao_path), "sha256": aosh},
            "b": {"path": str(bo_path), "sha256": bosh},
        }
        result["origin_comparison"] = base.compare_origins(ao, bo)
        result["finding_details"] = detail_origins(ao, bo)
    else:
        result["origin_comparison"] = "indisponivel: não prova igualdade de achados"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    forecast, forecast_hash = read(HERE / "forecast-frozen.json")
    clarification, clarification_hash = read(HERE / "protocol-clarification.json")
    if clarification["forecast_sha256"] != forecast_hash:
        raise ValueError("Previsao nao corresponde ao protocolo")
    out: dict[str, Any] = {
        "forecast_sha256": forecast_hash,
        "protocol_clarification_sha256": clarification_hash,
        "limitations": [
            "Identidades são limitadas aos aliases e atributos coletados; "
            "presença de Authorization não comprova identidade por pedido.",
            "Campos ausentes ou nulos não provam igualdade; parâmetros e "
            "evidências integrais não são comparados.",
            "A exclusão 40026 exige skipped/other/zero igual na referência.",
        ],
        "quality_evidence_limits": {
            "authorization": (
                "Contagens da auditoria nao provam conformidade de cada concessao, janela ou taxa; "
                "requer conferencia propria e provas de revogacao/limites. "
                "Fixture de aprovacao e somente de laboratorio."
            ),
            "planned_coverage": (
                "Perfis, plano, politica, limites e probe sao comparados; "
                "pontos de entrada e precondicoes ausentes nao sao inferidos."
            ),
            "executed_coverage": (
                "Operacoes e regras sao contadas; lacunas e valores ausentes exigem revisao. "
                "A 40026 e lacuna historica, nao executada."
            ),
            "detection": (
                "Achados e atributos disponiveis sao comparados; a existencia das classes "
                "de controle exige conferir controles independentes."
            ),
            "false_positives": (
                "T4 vulneravel nao prova modo seguro; comparar controles seguros independentes "
                "disponiveis e registrar qualquer falta."
            ),
            "state_identity": (
                "Aliases e atribuicoes sao comparados, mas Authorization nao atesta identidade "
                "efetiva; criacao de recursos e estado completo exigem evidencia propria."
            ),
        },
        "products": {},
    }
    for product in ("clinica-piloto", "vampi"):

        def name(variant: str, product: str = product) -> str:
            return f"v17-t4-{product}-vulnerable-1-{variant}"

        new_a, new_b = (args.new / (name(v) + ".json") for v in ("A", "B"))
        old_a, old_b = (args.historical / (name(v) + ".json") for v in ("A", "B"))
        suffix = "clinica" if product == "clinica-piloto" else "vampi"
        old_a_origins = CLOSURE / f"baseline-origins-{suffix}.json"
        new_a_origins, new_b_origins = (args.new / (name(v) + "-origins.json") for v in ("A", "B"))
        old_b_origins = HERE / f"baseline-b-origins-{suffix}.json"
        aa = compare(old_a, new_a, old_a_origins, new_a_origins)
        bb = compare(old_b, new_b, old_b_origins, new_b_origins)
        frozen_a = forecast["products"][product]["t4_a"]
        if (
            aa["sources"]["a"]["sha256"] != frozen_a["sha256"]
            or aa["run_ids"]["a"] != frozen_a["run_id"]
        ):
            raise ValueError("T4 A historica nao corresponde a previsao congelada")
        ab = compare(new_a, new_b, new_a_origins, new_b_origins)
        a, b = ab["scan_seconds"]["a"], ab["scan_seconds"]["b"]
        predicted = forecast["products"][product]["predicted_gain_pct"]
        historical_a = aa["scan_seconds"]["a"]
        gain = (1 - b / a) * 100
        historical_gain = (1 - b / historical_a) * 100
        out["products"][product] = {
            "v17_a_vs_new_a": aa,
            "v17_b_vs_new_b": bb,
            "new_a_vs_new_b": ab,
            "a_within_5_percent": a <= aa["scan_seconds"]["a"] * 1.05,
            "gain_pct": gain,
            "predicted_gain_pct": predicted,
            "absolute_error_pp": abs(gain - predicted),
            "historical_a_gain_pct": historical_gain,
            "historical_a_absolute_error_pp": abs(historical_gain - predicted),
            "both_error_gates_pass": abs(gain - predicted) <= 10
            and abs(historical_gain - predicted) <= 10,
        }
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
