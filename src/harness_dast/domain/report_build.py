"""Monta o `FindingsReport` a partir dos artefatos da execução (sem I/O).

Entradas: `probe.json`, `scan.json`, os alertas brutos já redigidos, a evidência já redigida, a
triagem opcional e o relatório de outra execução, opcional, para comparar. Este módulo é puro.
"""

from collections import Counter
from collections.abc import Mapping, Sequence

from pydantic import ValidationError

from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.finding import Finding
from harness_dast.domain.finding_build import AlertResolver, OperationRef, build_findings
from harness_dast.domain.finding_diff import compare_findings, ensure_comparable
from harness_dast.domain.finding_group import group_findings
from harness_dast.domain.internal_error_signals import classify_internal_error_signals
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.redaction import EvidenceMessage
from harness_dast.domain.report_labels import SEED_ASK_NOTICE
from harness_dast.domain.report_model import (
    NOT_TESTED_NEGATIVE,
    NOT_TESTED_STATEMENTS,
    NOT_TESTED_WITH_AUTHZ,
    ComparisonInfo,
    Coverage,
    FindingsReport,
    FindingsSummary,
    GoneFinding,
    NotTested,
    SeededScan,
    TruncatedScan,
)
from harness_dast.domain.scan_config import EXTRA_OUTCOMES
from harness_dast.domain.scan_result import ScanResult
from harness_dast.domain.signal_result import ProxySignals
from harness_dast.domain.triage import TriageFile, merge_triage
from harness_dast.domain.zap_alert import RawAlert


def parse_alerts(raw: Sequence[Mapping[str, object]]) -> tuple[tuple[RawAlert, ...], int]:
    """Lê os alertas gravados; devolve os legíveis e quantos malformados foram ignorados."""
    alerts: list[RawAlert] = []
    unreadable = 0
    for item in raw:
        try:
            alerts.append(RawAlert.model_validate(item))
        except ValidationError:
            unreadable += 1
    return tuple(alerts), unreadable


def build_resolver(probe: ProbeResult, scan: ScanResult) -> AlertResolver:
    """Liga mensagens aprendidas e alertas de cada varredura às operações do `probe`."""
    seeds = {entry.operation_id: entry.seed_outcome for entry in scan.entries}
    refs = {
        item.operation_id: OperationRef(
            operation_id=item.operation_id,
            method=item.method,
            path=item.path,
            seed_outcome=seeds.get(item.operation_id),
        )
        for item in probe.operations
    }
    by_message = {
        learned.message_id: refs[learned.operation_id]
        for learned in scan.learned
        if learned.operation_id in refs
    }
    by_alert = {
        alert_id: refs[entry.operation_id]
        for entry in scan.entries
        if entry.operation_id in refs
        for alert_id in entry.alert_ids
    }
    return AlertResolver(by_message, by_alert, tuple(refs.values()))


def _not_tested(probe: ProbeResult, scan: ScanResult) -> tuple[NotTested, ...]:
    scanned = {entry.operation_id for entry in scan.entries if entry.outcome != "refused"}
    refused = {entry.operation_id: entry for entry in scan.entries if entry.outcome == "refused"}
    skipped = {item.operation_id: item for item in scan.skipped}
    found: list[NotTested] = []
    for item in probe.operations:
        if item.operation_id in scanned:
            continue
        skip = skipped.get(item.operation_id)
        refusal = refused.get(item.operation_id)
        expected_login = str(item.outcome) == "auth_rejected_expected"
        reason = "scan_refused" if refusal else skip.reason if skip else f"probe_{item.outcome}"
        message = (
            (refusal.note or "O ZAP recusou iniciar a varredura.")
            if refusal
            else skip.message
            if skip
            else (item.message or f"O probe terminou com {item.outcome}.")
        )
        if expected_login and skip and skip.reason == "not_success" and refusal is None:
            reason = "login"
            message = "O login não é varrido para evitar bloqueio da conta."
        if expected_login:
            message = "Recusa esperada das credenciais sintéticas no login. " + message
        elif item.message and skip and item.message != skip.message:
            message = f"{message} Resultado do probe: {item.message}"
        if item.status == 404 and refusal is None:
            if skip is None:
                reason = "scan_sem_registro"
                message = "Não há motivo de ausência de varredura registrado no scan."
            message = f"O probe observou HTTP 404. {message}"
        if reason == "not_success" and item.outcome in EXTRA_OUTCOMES - set(scan.include_outcomes):
            ask = SEED_ASK_NOTICE.format(outcome=item.outcome)
            message += f" {ask[0].upper()}{ask[1:]}"
        found.append(
            NotTested(
                operation_id=item.operation_id,
                method=item.method,
                path=item.path,
                reason=reason,
                message=message,
                probe_outcome=item.outcome,
            )
        )
    return tuple(found)


def _seeded_scans(probe: ProbeResult, scan: ScanResult) -> tuple[SeededScan, ...]:
    """Operações varridas a partir de uma resposta que não foi sucesso (ADR 0050)."""
    statuses = {item.operation_id: item.status for item in probe.operations}
    return tuple(
        SeededScan(
            operation_id=entry.operation_id,
            method=entry.method,
            path=entry.path,
            seed_outcome=entry.seed_outcome,
            probe_status=statuses.get(entry.operation_id),
        )
        for entry in scan.entries
        if entry.seed_outcome and entry.outcome != "refused"
    )


_DESIGN_SKIPS = frozenset(
    {
        "scope",
        "denied",
        "delete",
        "login",
        "mutating",
        "not_selected",
        "upload_scan_not_authorized",
        "multipart_not_scannable",
    }
)
_DESIGN_OUTCOMES = frozenset({"skipped_scope", "skipped_denied", "skipped_destructive"})


def coverage_gaps(probe: ProbeResult, scan: ScanResult) -> tuple[NotTested, ...]:
    """Lacunas elegíveis, sem confundir exclusões do plano com falhas de cobertura."""
    return tuple(
        item
        for item in _not_tested(probe, scan)
        if item.reason not in _DESIGN_SKIPS and item.probe_outcome not in _DESIGN_OUTCOMES
    )


def coverage_is_partial(probe: ProbeResult, scan: ScanResult) -> bool:
    """Marca lacunas de alcance ou varredura sem contar exclusões deliberadas."""
    skips = {item.operation_id: item.reason for item in scan.skipped}
    unreached = any(
        item.outcome not in {"success", "auth_rejected_expected"}
        and item.outcome not in _DESIGN_OUTCOMES
        and skips.get(item.operation_id) not in _DESIGN_SKIPS
        for item in probe.operations
    )
    return (
        probe.status != "completed"
        or scan.status != "completed"
        or unreached
        or bool(coverage_gaps(probe, scan))
        or any(entry.outcome != "completed" for entry in scan.entries)
        or bool(scan.rule_coverage_gaps)
        or (scan.rule_coverage_gaps is None and any(e.outcome != "refused" for e in scan.entries))
        or scan.traffic.denied_by_reason.get("rate_backoff", 0) > 0
    )


def _coverage(probe: ProbeResult, scan: ScanResult) -> Coverage:
    summary = probe.summary
    return Coverage(
        operations_total=summary.operations_total,
        operations_sent=summary.operations_sent,
        probe_successes=summary.successes,
        probe_reached=summary.successes + summary.by_outcome.get("auth_rejected_expected", 0),
        reachability=summary.reachability,
        reachability_all=summary.reachability_all,
        partial=coverage_is_partial(probe, scan),
        rule_coverage_gaps=scan.rule_coverage_gaps,
        probe_status=probe.status,
        scan_status=scan.status,
        scan_stop_message=scan.stop_message,
        scans_run=sum(entry.outcome != "refused" for entry in scan.entries),
        truncated_scans=tuple(
            TruncatedScan(operation_id=e.operation_id, outcome=e.outcome, progress=e.progress)
            for e in scan.entries
            if e.outcome in {"truncated", "stopped"}
        ),
        not_tested=_not_tested(probe, scan),
        include_outcomes=scan.include_outcomes,
        seeded_scans=_seeded_scans(probe, scan),
        limits=scan.limits,
        policy=scan.policy,
        traffic=scan.traffic,
    )


_SEVERITIES = ("high", "medium", "low", "informational", "unknown")


def _summary(
    findings: Sequence[Finding],
    unreadable: int,
    authz: AuthzResult | None,
    signals: ProxySignals | None,
    negative: NegativeResult | None = None,
) -> FindingsSummary:
    counts: Counter[str] = Counter(item.proposed_severity for item in findings)
    own: Counter[str] = Counter(
        item.proposed_severity for item in (authz.findings if authz else ())
    )
    typed: Counter[str] = Counter(
        item.proposed_severity for item in (negative.findings if negative else ())
    )
    seen: Counter[str] = Counter(
        item.proposed_severity for item in (signals.findings if signals else ())
    )
    return FindingsSummary(
        total=len(findings),
        by_severity={name: counts.get(name, 0) for name in _SEVERITIES},
        occurrences=sum(item.occurrences for item in findings),
        alerts_unreadable=unreadable,
        authz_by_severity=({name: own.get(name, 0) for name in _SEVERITIES} if authz else {}),
        negative_by_severity=(
            {name: typed.get(name, 0) for name in _SEVERITIES} if negative else {}
        ),
        signal_by_severity=(
            {name: seen.get(name, 0) for name in _SEVERITIES} if signals and signals.enabled else {}
        ),
    )


def _statements(authz: AuthzResult | None, negative: NegativeResult | None) -> tuple[str, ...]:
    base = NOT_TESTED_STATEMENTS if authz is None else NOT_TESTED_WITH_AUTHZ
    return base if negative is None else (*base, NOT_TESTED_NEGATIVE)


def assemble_report(
    *,
    probe: ProbeResult,
    scan: ScanResult,
    raw_alerts: Sequence[Mapping[str, object]],
    evidence: Mapping[int, EvidenceMessage],
    triage: TriageFile | None,
    baseline: FindingsReport | None,
    generated_at: str,
    harness_version: str,
    auth_header: tuple[str, str] | None,
    csrf_header: str | None,
    authz: AuthzResult | None = None,
    proxy_signals: ProxySignals | None = None,
    negative: NegativeResult | None = None,
) -> FindingsReport:
    """Monta o relatório completo.

    Raises:
        ConfigError: A execução de comparação é de outro produto ou de outra versão do
            fingerprint.
    """
    alerts, unreadable = parse_alerts(raw_alerts)
    findings = build_findings(
        alerts,
        product=probe.product,
        resolver=build_resolver(probe, scan),
        evidence=evidence,
        auth_header=auth_header,
        csrf_header=csrf_header,
    )
    orphans: tuple[str, ...] = ()
    if triage is not None:
        findings, orphans = merge_triage(findings, triage)
        supplemental = frozenset(
            finding.fingerprint
            for source in (authz, proxy_signals, negative)
            if source is not None
            for finding in source.findings
        )
        orphans = tuple(fingerprint for fingerprint in orphans if fingerprint not in supplemental)
    gone: tuple[GoneFinding, ...] = ()
    comparison: ComparisonInfo | None = None
    if baseline is not None:
        ensure_comparable(baseline, probe.product)
        scanned = {entry.operation_id for entry in scan.entries if entry.outcome != "refused"}
        findings, gone, comparison = compare_findings(findings, baseline, scanned)
    return FindingsReport(
        run_id=probe.run_id,
        product=probe.product,
        generated_at=generated_at,
        harness_version=harness_version,
        coverage=_coverage(probe, scan),
        summary=_summary(findings, unreadable, authz, proxy_signals, negative),
        findings=findings,
        groups=group_findings(findings),
        not_observed=gone,
        comparison=comparison,
        triage_orphans=orphans,
        authz=authz,
        proxy_signals=proxy_signals,
        negative=negative,
        internal_error_signals=classify_internal_error_signals(evidence),
        not_tested_statements=_statements(authz, negative),
    )
