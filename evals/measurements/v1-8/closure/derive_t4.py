"""Produz comparação sanitizada T4 a partir dos registros e fontes explícitas."""

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from runpy import run_path
from typing import Any

HERE = Path(__file__).resolve().parent
OLD = Path(r"C:\harness-dast-artefatos\v1.7-velocidade\lab")
NEW = Path(r"C:\harness-dast-artefatos\v1-8\closure\t4-measurements")
MISSING = "__ausente__"


def load(path: Path) -> Any:
    """Lê JSON sem imprimir ou copiar conteúdo não selecionado."""
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    """Identifica os bytes da fonte."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix(record: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    """Extrai cada operação/regra, com nulos e ausências explícitos."""
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for operation in (record.get("rule_stats") or {}).get("operations", []):
        for rule in operation.get("rules", []):
            ident = rule.get("plugin_id")
            if ident == 40026:
                continue
            key = (operation["operation_id"], ident)
            if key in result:
                raise ValueError(f"Regra duplicada: {key}")
            result[key] = {
                k: rule.get(k, MISSING)
                for k in ("state", "requests", "alerts", "time_ms", "skip_reason")
            }
    return result


def paired_rules(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    """Gera matriz integral; ausência nunca representa zero."""
    left, right = matrix(a), matrix(b)
    return [
        {"operation_id": k[0], "plugin_id": k[1], "a": left.get(k), "b": right.get(k)}
        for k in sorted(left.keys() | right.keys())
    ]


def rows(record: dict[str, Any], key: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    """Extrai apenas campos acordados dos registros."""
    source = record.get(key, [])
    return [{field: item.get(field, MISSING) for field in fields} for item in source]


def histogram(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conserva multiplicidades sem depender de ordem."""
    counts = Counter(json.dumps(item, sort_keys=True, ensure_ascii=False) for item in items)
    return [{"item": json.loads(k), "count": v} for k, v in sorted(counts.items())]


def stage(origin: dict[str, Any], name: str) -> dict[str, Any]:
    """Lê authz ou negative autorizado e publica somente totais e chaves de controle."""
    ref = origin["sources"][name]
    path = Path(ref["path"])
    if digest(path) != ref["sha256"]:
        raise ValueError(f"Hash divergente: {path}")
    data = load(path)
    if data.get("run_id") != origin["run_id"]:
        raise ValueError("Run incompatível")
    result = {k: data.get(k, MISSING) for k in ("status", "requests_sent")}
    keys = {
        "checks": ("check", "status", "candidates", "tested", "findings"),
        "by_class": (
            "case_class",
            "planned",
            "sent",
            "rejected",
            "accepted",
            "server_error",
            "inconclusive",
        ),
        "operations": (
            "operation_id",
            "method",
            "path",
            "sent",
            "rejected",
            "accepted",
            "server_error",
            "inconclusive",
        ),
        "not_tested": ("check", "operation_id", "method", "path", "reason", "case_class"),
    }
    for key, fields in keys.items():
        if key in data:
            result[key] = histogram(rows(data, key, fields))
    return result


def duration(record: dict[str, Any]) -> float:
    """Calcula segundos pela mesma definição temporal da V1.7."""
    scan = record["scan"]
    return (
        datetime.fromisoformat(scan["finished_at"]) - datetime.fromisoformat(scan["started_at"])
    ).total_seconds()


def build(product: str) -> dict[str, Any]:
    """Compara uma API sem inferir equivalência a partir de dados ausentes."""
    a_path = OLD / f"v17-t4-{product}-vulnerable-1-A.json"
    b_path = NEW / f"v17-t4-{product}-vulnerable-1-B.json"
    suffix = "clinica" if product == "clinica-piloto" else "vampi"
    oa_path = HERE / f"baseline-origins-{suffix}.json"
    ob_path = NEW / f"v17-t4-{product}-vulnerable-1-B-origins.json"
    a, b, oa, ob = map(load, (a_path, b_path, oa_path, ob_path))
    for origin in (oa, ob):
        for source in origin["sources"].values():
            path = Path(source["path"])
            if digest(path) != source["sha256"]:
                raise ValueError(f"Hash divergente: {path}")
    forecast = load(HERE / "forecast-frozen.json")["products"][product]
    if a["manifest"]["run_id"] != oa["run_id"] or b["manifest"]["run_id"] != ob["run_id"]:
        raise ValueError("Matriz de origem e execução divergentes")
    if (
        a["manifest"]["run_id"] != forecast["t4_a"]["run_id"]
        or digest(a_path) != forecast["t4_a"]["sha256"]
    ):
        raise ValueError("Referência A não corresponde à previsão congelada")
    tool = run_path(str(HERE / "compare_v18.py"))
    wall_a, wall_b = duration(a), duration(b)
    gain = 100 * (1 - wall_b / wall_a)
    predicted = forecast["predicted_gain_pct"]
    probe_fields = (
        "operation_id",
        "method",
        "path",
        "outcome",
        "status",
        "account",
        "attempts",
        "blocked_dependencies",
    )
    account_fields = ("phase", "route", "decision", "operation_id", "account", "method")
    config = {}
    for label, record in (("a", a), ("b", b)):
        config[label] = {
            "profile": record.get("profile"),
            "policy": record["scan"].get("policy"),
            "scan_limits": record["scan"].get("limits"),
            "manifest_accounts": record["manifest"].get("accounts", MISSING),
            "zap_version": record["manifest"].get("zap_version", MISSING),
            "harness_version": record["manifest"].get("harness_version", MISSING),
        }
    return {
        "product": product,
        "sources": {
            label: {"path": str(path), "sha256": digest(path)}
            for label, path in (
                ("t4_a", a_path),
                ("t4_b", b_path),
                ("origins_a", oa_path),
                ("origins_b", ob_path),
            )
        },
        "runs": {"a": oa["run_id"], "b": ob["run_id"]},
        "wall_seconds": {"a": wall_a, "b": wall_b},
        "gain_pct": {
            "predicted": predicted,
            "observed": gain,
            "absolute_error_percentage_points": abs(gain - predicted),
        },
        "decision": "não promover: erro acima de 10 pontos percentuais"
        if abs(gain - predicted) > 10
        else "previsão dentro de 10 p.p.; qualidade independente pendente",
        "config": config,
        "comparison": tool["compare"](a, b),
        "origins": tool["compare_origins"](oa, ob),
        "rules": paired_rules(a, b),
        "probe": {
            "a": histogram(rows(a, "probe", probe_fields)),
            "b": histogram(rows(b, "probe", probe_fields)),
        },
        "accounts": {
            "a": histogram(rows(a, "accounts", account_fields)),
            "b": histogram(rows(b, "accounts", account_fields)),
        },
        "scanner_observations": {
            label: {
                "auth_on_scanner": record.get("auth_on_scanner", MISSING),
                "csrf": record.get("csrf", MISSING),
            }
            for label, record in (("a", a), ("b", b))
        },
        "stages": {
            name: {"a": stage(oa, name), "b": stage(ob, name)} for name in ("authz", "negative")
        },
        "limitations": [
            "Pontos e valores efetivos indisponiveis: entrada nao comprovada.",
            "Apelidos e auditoria nao comprovam identidade em cada pedido.",
            "Pedidos e alertas podem variar; diferenças são preservadas e exigem revisão.",
            "DOM XSS 40026 excluida; cobertura no navegador nao demonstrada.",
        ],
    }


def main() -> None:
    """Grava resultados em arquivos novos, sem alterar previsão."""
    for product in ("clinica-piloto", "vampi"):
        path = HERE / f"t4-comparison-{product}.json"
        with path.open("x", encoding="utf-8") as output:
            json.dump(build(product), output, ensure_ascii=False, indent=2)
            output.write("\n")


if __name__ == "__main__":
    main()
