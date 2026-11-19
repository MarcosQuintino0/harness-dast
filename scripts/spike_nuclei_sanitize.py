"""Spike do Nuclei (nunca na main): projeta a saída `-jsonl` do Nuclei sem nenhum segredo.

Lista branca de campos. Descarta `curl-command`, `request`, `response` e `extracted-results`; de um valor extraído
(possível segredo exposto) guarda só o tipo e o tamanho em bytes. A severidade segue o mapa fixo do plano
(critical/high -> alta, medium -> média, low -> baixa, info/unknown -> informativa).

Uso: spike_nuclei_sanitize.py ENTRADA.jsonl [MARCADOR ...]  (os marcadores só servem à verificação: nenhum pode
aparecer na saída serializada).
"""

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

SEVERITY = {"critical": "alta", "high": "alta", "medium": "media", "low": "baixa", "info": "informativa", "unknown": "informativa"}
FORBIDDEN_KEYS = ("curl-command", "request", "response", "extracted-results")


def sanitize(record: dict[str, object]) -> dict[str, object]:
    info = record.get("info")
    severity = str(info.get("severity", "unknown")) if isinstance(info, dict) else "unknown"
    out: dict[str, object] = {
        "template_id": str(record.get("template-id", "")),
        "severity": SEVERITY.get(severity, "informativa"),
        "path": urlsplit(str(record.get("matched-at", ""))).path or "/",
    }
    extracted = record.get("extracted-results")
    if isinstance(extracted, list) and extracted:
        out["secret_type"] = "extracted_value"
        out["secret_count"] = len(extracted)
        out["secret_length_bytes"] = sum(len(str(value).encode("utf-8")) for value in extracted)
    return out


def main(path: str, markers: list[str]) -> None:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.startswith("{")]
    rows = [row for row in rows if "template-id" in row]
    cleaned = [sanitize(row) for row in rows]
    serialized = json.dumps(cleaned, ensure_ascii=False)
    raw_keys = sorted({key for row in rows for key in FORBIDDEN_KEYS if key in row})
    print(f"registros: {len(rows)}; chaves sensiveis presentes na saida bruta: {raw_keys}")
    print("chaves sensiveis na saida limpa:", [key for key in FORBIDDEN_KEYS if key in serialized])
    for marker in markers:
        print(f"marcador {marker[:6]}...: na bruta={marker in Path(path).read_text(encoding='utf-8')} na limpa={marker in serialized}")
    for row in cleaned:
        if "secret_type" in row or row["template_id"] in {"aws-access-key-value", "springboot-env"}:
            print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
