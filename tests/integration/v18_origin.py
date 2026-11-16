"""Extrai somente campos públicos de origem dos artefatos da execução do laboratório."""

import hashlib
import json
from pathlib import Path
from typing import Any

_FIELDS = ("title", "plugin_id", "technique", "operation_id", "method", "path_template")


def collect_origins(run_dir: Path) -> dict[str, Any]:
    """Separa achados do ZAP, authz e negative pelas fontes, sem copiar evidências."""
    result: dict[str, Any] = {"run_id": run_dir.name, "sources": {}}
    for origin, name in (
        ("zap", "findings.json"),
        ("authz", "authz.json"),
        ("negative", "negative.json"),
    ):
        path = run_dir / name
        if not path.exists():
            result["sources"][origin] = {"status": "ausente", "findings": []}
            continue
        raw = path.read_bytes()
        source = json.loads(raw)
        if source.get("run_id") != run_dir.name or not isinstance(source.get("findings"), list):
            raise ValueError(f"Artefato {name} não corresponde à execução ou não tem achados")
        result["sources"][origin] = {
            "status": source.get("status", "disponivel"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "path": str(path),
            "findings": [{key: row.get(key) for key in _FIELDS} for row in source["findings"]],
        }
    return result
