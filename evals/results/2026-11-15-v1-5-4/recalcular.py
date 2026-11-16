"""Recalcula somente (f) a partir de score.json publico e trace sanitizado."""

import hashlib
import json
import sys
from pathlib import Path

from evals.runner.checks_triage import triage_component
from evals.runner.models import Component
from evals.runner.scoring import final_grade

ROOT = Path(r"C:\harness-dast-artefatos\rodadas-cegas")
ROUNDS = (
    "piloto-terra61-v153-random-2026-11-15",
    "piloto-sonnet55-v153-vuln-2026-11-15",
)


def main() -> None:
    """Imprime somente notas, checks e hash da nota pública anterior."""
    result = []
    for name in ROUNDS:
        folder = ROOT / name
        raw = (folder / "score.json").read_bytes()
        original = json.loads(raw)
        triage = triage_component(folder / "trace")
        components = [
            triage if item["id"] == "triage" else Component.model_validate(item)
            for item in original["components"]
        ]
        old_triage = next(c for c in original["components"] if c["id"] == "triage")
        result.append(
            {
                "round": name,
                "score_sha256": hashlib.sha256(raw).hexdigest(),
                "before": original["grade"],
                "after": round(
                    final_grade(components, widening=original["widening_cap_applied"]), 2
                ),
                "triage_before": old_triage["score"],
                "triage_after": triage.score,
                "checks_after": {check.id: check.passed for check in triage.checks},
            }
        )
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
