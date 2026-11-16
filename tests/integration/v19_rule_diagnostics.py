"""Metadados exportáveis da investigação dirigida, sem valores ou mensagens HTTP."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from tests.integration.lab_support import REPO


def baseline_rules() -> list[int]:
    """Obtém o inventário histórico, sem escolher pelo resultado dos controles."""
    path = REPO / "evals/measurements/v1-8/round3/t4-comparison.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    counts = data["products"]["clinica-piloto"]["v17_a_vs_new_a"]["counts"]["rules"]["a"]
    return sorted({int(json.loads(key)[1]) for key in counts})


def _shape(value: object) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    text = str(value)
    for name, needle in (("polyglot", "<%="), ("polyglot", "<th:t="), ("math", "zj")):
        if needle in text:
            return name
    if text in {"", "@", "+", "\x00", "|"}:
        return {"": "empty", "@": "at", "+": "plus", "\x00": "nul", "|": "pipe"}[text]
    return type(value).__name__


def message_metadata(message: dict[str, Any]) -> dict[str, Any]:
    """Reduz em memória a classes fechadas, nomes de campos, tamanhos e status."""
    first = str(message["requestHeader"]).splitlines()[0].split(" ")
    parsed = urlsplit(first[1])
    body = str(message.get("requestBody", ""))
    try:
        value = json.loads(body) if body else {}
    except json.JSONDecodeError:
        value = {}
    fields = (
        {str(key): _shape(item) for key, item in value.items()} if isinstance(value, dict) else {}
    )
    response = str(message.get("responseBody", ""))
    header = str(message["responseHeader"]).splitlines()[0].split(" ")
    return {
        "method": first[0],
        "path_segment_classes": [_shape(unquote(segment)) for segment in parsed.path.split("/")],
        "query_fields": {
            key: _shape(item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        },
        "body_fields": fields,
        "request_body_length": len(body),
        "response_status": int(header[1]),
        "response_body_length": len(response),
    }


def summarize_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Conta vetores e status sem publicar IDs, cabeçalhos, corpos ou valores."""
    rows = [message_metadata(message) for message in messages if str(message["type"]) == "14"]
    return {
        "count": len(rows),
        "statuses": dict(Counter(str(row["response_status"]) for row in rows)),
        "messages": rows,
    }


def source_hashes() -> dict[str, str]:
    """Vincula a revisão pública do add-on consultada antes da prova."""
    root = Path("C:/harness-dast-artefatos/v1-9/sources")
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.glob("*.java"))
    }
