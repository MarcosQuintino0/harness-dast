"""Construtores de `ProbeResult` e `ScanResult` mínimos para testar o relatório sem I/O."""

from collections.abc import Sequence

from harness_dast.domain.probe_result import OperationResult, ProbeResult, summarize_results
from harness_dast.domain.run import RunLimits
from harness_dast.domain.scan_config import ScanConfig
from harness_dast.domain.scan_plan import LearnedRef, ScanSkip
from harness_dast.domain.scan_policy import build_limits, build_policy
from harness_dast.domain.scan_result import (
    AppliedLimits,
    AppliedPolicy,
    HealthSummary,
    ScanEntry,
    ScanResult,
)

RUN_ID = "2026-11-13T05-15-32Z-vampi-ab12"
OTHER_RUN_ID = "2026-11-12T05-15-32Z-vampi-cd34"


def operation(
    operation_id: str, method: str, path: str, outcome: str = "success", **extra: object
) -> OperationResult:
    return OperationResult.model_validate(
        {
            "operation_id": operation_id,
            "method": method,
            "path": path,
            "outcome": outcome,
            "status": 200 if outcome == "success" else None,
            **extra,
        }
    )


def probe_result(operations: Sequence[OperationResult], run_id: str = RUN_ID) -> ProbeResult:
    return ProbeResult(
        run_id=run_id,
        product="vampi",
        dry_run=False,
        status="completed",
        seed=1,
        started_at="2026-11-13T05:15:32+00:00",
        finished_at="2026-11-13T05:16:00+00:00",
        summary=summarize_results(operations, len(operations)),
        operations=tuple(operations),
    )


def entry(
    operation_id: str,
    method: str,
    path: str,
    message_id: int,
    outcome: str = "completed",
    alert_ids: tuple[str, ...] = (),
    seed_outcome: str | None = None,
) -> ScanEntry:
    return ScanEntry.model_validate(
        {
            "operation_id": operation_id,
            "method": method,
            "path": path,
            "message_id": message_id,
            "scan_id": "0",
            "outcome": outcome,
            "progress": 100 if outcome == "completed" else 45,
            "truncated": outcome == "truncated",
            "duration_seconds": 3.5,
            "requests": 120,
            "alert_count": len(alert_ids),
            "alert_ids": alert_ids,
            "seed_outcome": seed_outcome,
        }
    )


def scan_result(
    entries: Sequence[ScanEntry],
    learned: Sequence[LearnedRef] = (),
    skipped: Sequence[ScanSkip] = (),
    run_id: str = RUN_ID,
    status: str = "completed",
    include_outcomes: tuple[str, ...] = (),
) -> ScanResult:
    limits = RunLimits(requests_per_second=5, max_duration_minutes=60, zap_threads_per_host=2)
    config = ScanConfig()
    return ScanResult.model_validate(
        {
            "run_id": run_id,
            "product": "vampi",
            "dry_run": False,
            "status": status,
            "started_at": "2026-11-13T05:16:10+00:00",
            "finished_at": "2026-11-13T05:20:00+00:00",
            "policy": AppliedPolicy.from_policy(build_policy(config)),
            "limits": AppliedLimits.from_limits(limits, build_limits(limits, config)),
            "entries": tuple(entries),
            "skipped": tuple(skipped),
            "learned": tuple(learned),
            "health": HealthSummary(enabled=True, checks=4),
            "include_outcomes": include_outcomes,
        }
    )
