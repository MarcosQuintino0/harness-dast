"""Compara controles seguros publicados sem copiar auditoria bruta nem duração."""

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OLD = Path(r"C:\harness-dast-artefatos\v1.7-velocidade\lab")
NEW = HERE / "other-controls"
NEGATIVE_FIELDS = (
    "exit_code",
    "status",
    "stop_message",
    "requests_sent",
    "operations_tested",
    "accounts",
    "created_resources",
    "restored_resources",
    "by_class",
    "response_status_counts",
    "status_families",
    "requests_by_method",
    "proxy_denials_by_reason",
    "unexpected_proxy_denials",
    "cli_429_results",
    "restore_requests",
    "findings",
    "operations",
    "not_tested_by_reason",
)


def read(path: Path) -> dict[str, Any]:
    """Lê fonte JSON sanitizada."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"Objeto esperado: {path}")
    return data


def source(path: Path, run_id: str | None) -> dict[str, Any]:
    """Identifica fonte e run, quando disponível."""
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "run_id": run_id,
    }


def comparison(a: dict[str, Any], b: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Preserva valores e marca dados faltantes sem presumir igualdade."""
    result = {}
    for key in fields:
        if key not in a or key not in b:
            result[key] = {
                "status": "indisponivel",
                "a_present": key in a,
                "b_present": key in b,
                "a": a.get(key),
                "b": b.get(key),
            }
        elif a[key] is None or b[key] is None:
            result[key] = {
                "status": "nulo_ambos" if a[key] is b[key] else "diferente",
                "a": a[key],
                "b": b[key],
            }
        else:
            result[key] = {
                "status": "igual" if a[key] == b[key] else "diferente",
                "a": a[key],
                "b": b[key],
            }
    return result


def negative() -> dict[str, Any]:
    """Compara somente rounds.write, incluindo achados existentes."""
    a_path = OLD / "controls-recheck/lab-negative-secure.json"
    b_path = NEW / "v18-b-negative-write-clinica-piloto-secure.json"
    a, b = read(a_path), read(b_path)
    return {
        "sources": {"a": source(a_path, None), "b": source(b_path, b.get("run_id"))},
        "context": comparison(a, b, ("mode",)),
        "fields": comparison(a["rounds"]["write"], b["rounds"]["write"], NEGATIVE_FIELDS),
        "limitations": [
            "A nao registra run_id no resumo.",
            "Nove achados baixos ja constam em A e B; nao se declara o modo seguro limpo.",
            "Duracoes nao foram comparadas.",
        ],
    }


def cors(product: str) -> dict[str, Any]:
    """Compara resumo CORS e número de achados por API."""
    a_path = OLD / f"lab-cors-{product}-secure.json"
    b_path = NEW / f"v18-b-cors-{product}-secure.json"
    a, b = read(a_path), read(b_path)
    a_summary, b_summary = a.get("summary", {}), b.get("summary", {})
    fields = tuple(sorted(a_summary.keys() | b_summary.keys()))
    findings_a = (
        {"findings_count": len(a["findings"])} if isinstance(a.get("findings"), list) else {}
    )
    findings_b = {"findings_count": b["findings_count"]} if "findings_count" in b else {}
    return {
        "sources": {"a": source(a_path, a.get("run_id")), "b": source(b_path, b.get("run_id"))},
        "context": comparison(a, b, ("product", "mode")),
        "summary": comparison(a_summary, b_summary, fields),
        "findings_count": comparison(findings_a, findings_b, ("findings_count",)),
        "limitations": [
            "A nao registra run_id no resumo.",
            "Sem achados CORS nao implica ausencia de outros achados.",
        ],
    }


def main() -> None:
    """Gera arquivo novo sem modificar provas e previsões."""
    result = {
        "negative_write_clinica_secure": negative(),
        "cors_clinica_secure": cors("clinica-piloto"),
        "cors_vampi_secure": cors("vampi"),
    }
    with (HERE / "other-controls-comparison.json").open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
