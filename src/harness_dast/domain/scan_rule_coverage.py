"""Lacunas de cobertura de regras, sem texto externo nem I/O."""

from typing import Literal

from harness_dast.domain.rule_stats import OperationRules
from harness_dast.domain.scan_result import RuleCoverageGap, ScanEntry


def rule_coverage_gaps(
    entries: tuple[ScanEntry, ...], stats: tuple[OperationRules, ...]
) -> tuple[RuleCoverageGap, ...]:
    """Converte medições em lacunas; nenhum registro ou lista vazia é prova de cobertura."""
    by_scan = {item.scan_id: item for item in stats}
    gaps: list[RuleCoverageGap] = []
    for entry in entries:
        if entry.outcome == "refused":
            continue
        item = by_scan.get(entry.scan_id) if entry.scan_id is not None else None
        if (
            item is None
            or item.operation_id != entry.operation_id
            or item.unavailable_reason is not None
            or not item.rules
        ):
            gaps.append(
                RuleCoverageGap(
                    operation_id=entry.operation_id, state="unavailable", reason="stats_unavailable"
                )
            )
            continue
        for rule in item.rules:
            if rule.state == "completed":
                continue
            reason: Literal["max_rule_time", "other", "incomplete"] = (
                "max_rule_time"
                if rule.state == "skipped" and rule.skip_reason == "max_rule_time"
                else "other"
                if rule.state == "skipped"
                else "incomplete"
            )
            gaps.append(
                RuleCoverageGap(
                    operation_id=entry.operation_id,
                    plugin_id=rule.plugin_id,
                    state=rule.state,
                    reason=reason,
                )
            )
    return tuple(gaps)
