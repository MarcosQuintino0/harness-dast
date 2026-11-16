"""Compara atributos sanitizados dos achados originais, preservando incertezas."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
NEW = Path(r"C:\harness-dast-artefatos\v1-8\closure\t4-measurements")
FIELDS = (
    "title",
    "proposed_severity",
    "technique",
    "plugin_id",
    "operation_id",
    "method",
    "path_template",
    "location",
    "field",
    "fields",
    "case_class",
    "declared",
    "actor_account",
    "actor_role",
    "owner_account",
    "owner_role",
    "input_vector",
)


def read(path: Path) -> Any:
    """Lê arquivo de origem autorizado."""
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    """Calcula identificador do arquivo."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(reference: dict[str, Any], origin: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Valida fonte e seleciona somente atributos de achado sem evidência ou payload."""
    source = reference["sources"][origin]
    path = Path(source["path"])
    if not path.is_file() or sha(path) != source["sha256"]:
        raise ValueError(f"Fonte ausente ou alterada: {path}")
    data = read(path)
    if data.get("run_id") != reference["run_id"] or not isinstance(data.get("findings"), list):
        raise ValueError(f"Origem incompatível: {path}")
    findings = []
    for row in data["findings"]:
        selected = {}
        for key in FIELDS:
            if key not in row:
                selected[key] = {"state": "absent"}
            elif row[key] is None:
                selected[key] = {"state": "null"}
            else:
                selected[key] = {"state": "present", "value": row[key]}
        findings.append({"attributes": selected, "fingerprint": row.get("fingerprint")})
    return {
        "run_id": reference["run_id"],
        "path": str(path),
        "sha256": source["sha256"],
        "status": data.get("status", "available"),
    }, findings


def tally(rows: list[Any]) -> Counter[str]:
    """Conta itens por conteúdo em ordem determinística."""
    return Counter(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)


def paired(a: Counter[str], b: Counter[str]) -> list[dict[str, Any]]:
    """Lista contagens completas, sem tratar atributos ausentes como conhecidos."""
    return [{"value": json.loads(key), "a": a[key], "b": b[key]} for key in sorted(set(a) | set(b))]


def compare(product: str) -> dict[str, Any]:
    """Constrói as três comparações, por API e fonte."""
    suffix = "clinica" if product == "clinica-piloto" else "vampi"
    a_path = HERE / f"baseline-origins-{suffix}.json"
    b_path = NEW / f"v17-t4-{product}-vulnerable-1-B-origins.json"
    ref_a, ref_b = read(a_path), read(b_path)
    origins = {}
    for origin in ("zap", "authz", "negative"):
        meta_a, a = extract(ref_a, origin)
        meta_b, b = extract(ref_b, origin)
        attrs_a, attrs_b = tally([v["attributes"] for v in a]), tally([v["attributes"] for v in b])
        fps_a, fps_b = tally([v["fingerprint"] for v in a]), tally([v["fingerprint"] for v in b])
        origins[origin] = {
            "source_a": meta_a,
            "source_b": meta_b,
            "attribute_counts": paired(attrs_a, attrs_b),
            "attribute_difference_count": sum(
                attrs_a[key] != attrs_b[key] for key in set(attrs_a) | set(attrs_b)
            ),
            "fingerprint_counts": paired(fps_a, fps_b),
            "fingerprint_difference_count": sum(
                fps_a[key] != fps_b[key] for key in set(fps_a) | set(fps_b)
            ),
            "missing_fields": {
                field: {
                    "a": sum(row["attributes"][field]["state"] != "present" for row in a),
                    "b": sum(row["attributes"][field]["state"] != "present" for row in b),
                }
                for field in FIELDS
            },
        }
    return {
        "product": product,
        "sources": {"reference_a_sha256": sha(a_path), "reference_b_sha256": sha(b_path)},
        "origins": origins,
    }


def main() -> None:
    """Grava somente suplemento novo, mantendo previsões e resultados antigos."""
    output = {
        "limitations": [
            "Campos ausentes ou nulos sao desconhecidos e nao provam igualdade.",
            "Parameter omitido: pode conter valores concretos de recurso ou payload.",
            "Atributos e fingerprint iguais nao provam igualdade de evidencias ou identidade.",
        ],
        "products": [compare("clinica-piloto"), compare("vampi")],
    }
    with (HERE / "findings-comparison-detailed.json").open("x", encoding="utf-8") as path:
        json.dump(output, path, ensure_ascii=False, indent=2)
        path.write("\n")


if __name__ == "__main__":
    main()
