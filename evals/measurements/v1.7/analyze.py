"""Previsão por regra, antes de T4 B; dados são revisados e normalizados pelo operador."""

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, TypeGuard


def _positive(value: object) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def predict(data: dict[str, Any]) -> dict[str, Any]:
    """Exige todas as regras de T4 A e três ou cinco amostras completas em cada variante."""
    rules, wall = data.get("rules"), data.get("wall_a")
    if not isinstance(rules, dict) or not rules or not _positive(wall):
        return {"status": "inconclusivo", "reason": "regras ou parede A ausentes"}
    expected = data.get("expected_rule_ids")
    if not isinstance(expected, list) or not expected or set(expected) != set(rules):
        return {"status": "inconclusivo", "reason": "inventário completo de regras ausente"}
    weighted = total = 0.0
    for rule in rules.values():
        if not isinstance(rule, dict) or rule.get("complete") is not True:
            return {"status": "inconclusivo", "reason": "regra ausente ou truncada"}
        full, a, b = rule.get("full_a"), rule.get("t3_a"), rule.get("t3_b")
        if not _positive(full) or not isinstance(a, list) or not isinstance(b, list):
            return {"status": "inconclusivo", "reason": "tempo por regra ausente"}
        if len(a) not in (3, 5) or len(a) != len(b) or not all(map(_positive, a + b)):
            return {"status": "inconclusivo", "reason": "amostras ausentes ou inválidas"}
        total += full
        weighted += full * statistics.median(b) / statistics.median(a)
    estimated = wall * weighted / total
    return {"status": "previsão", "wall_b": estimated, "gain_pct": 100 * (wall - estimated) / wall}


if __name__ == "__main__":
    source = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    sys.stdout.write(json.dumps(predict(source), ensure_ascii=False, indent=2) + "\n")
