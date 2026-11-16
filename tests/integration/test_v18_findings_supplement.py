"""Confere que o suplemento não transforma ausência em valor conhecido."""

import hashlib
import json
from pathlib import Path
from runpy import run_path


def test_findings_extract_preserves_missing_null_and_omits_evidence(tmp_path: Path) -> None:
    script = Path("evals/measurements/v1-8/closure/derive_findings_v18.py")
    extract = run_path(str(script))["extract"]
    source = tmp_path / "findings.json"
    source.write_text(
        json.dumps(
            {
                "run_id": "run1",
                "findings": [{"title": "x", "location": None, "evidence": "private"}],
            }
        ),
        encoding="utf-8",
    )
    reference = {
        "run_id": "run1",
        "sources": {
            "zap": {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        },
    }
    _, findings = extract(reference, "zap")
    assert findings[0]["attributes"]["location"] == {"state": "null"}
    assert findings[0]["attributes"]["field"] == {"state": "absent"}
    assert "private" not in json.dumps(findings)
