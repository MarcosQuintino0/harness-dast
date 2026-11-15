"""Transforma as linhas da auditoria da cerca em contagens e achados de sinal (ADR 0049).

Entrada: as linhas da trilha do proxy (`ProxyRow`), o intervalo da execução e o `AlertResolver`
do `probe`. Só linhas LIBERADAS, com status, dentro do intervalo contam. A decisão de escopo
nunca passa por aqui: o sinal só observa. Nenhum valor de resposta existe nestas linhas (só a
categoria), então nenhum entra nos achados. Este módulo é puro.
"""

import hashlib
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime

from harness_dast.domain.error_signal_catalog import RULE_BY_CATEGORY, SIGNAL_RULES
from harness_dast.domain.finding import generic_template, normalize_path_template
from harness_dast.domain.finding_build import AlertResolver
from harness_dast.domain.signal_result import (
    MAX_QUERY_PARAMS,
    MAX_SIGNAL_FINDINGS,
    MAX_STATUSES,
    SIGNAL_FINGERPRINT_VERSION,
    ProxySignals,
    SignalFinding,
    SignalWindow,
)
from harness_dast.domain.traffic import ProxyRow
from harness_dast.domain.zap_alert import SEVERITY_RANK


def parse_instant(text: str) -> datetime | None:
    """Lê um instante ISO 8601 (sem fuso vale UTC); `None` se não for um instante."""
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def signal_window(
    started_at: str, finished: Sequence[str | None]
) -> tuple[datetime, datetime] | None:
    """Intervalo da execução: do início do `probe` ao último fim gravado; `None` se ilegível."""
    start = parse_instant(started_at)
    ends = [moment for text in finished if text and (moment := parse_instant(text)) is not None]
    if start is None or not ends:
        return None
    end = max(ends)
    return (start, end) if end >= start else None


def signal_fingerprint(*, product: str, method: str, path_template: str, category: str) -> str:
    """SHA-256 (hex): produto, método, modelo de caminho e categoria. Sem host, status ou ids."""
    parts = (
        f"hdast-signal-v{SIGNAL_FINGERPRINT_VERSION}",
        product,
        method.upper(),
        normalize_path_template(path_template),
        category,
    )
    payload = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _Group:
    """Acúmulo de um achado enquanto as linhas são lidas (não sai deste módulo)."""

    def __init__(self, row: ProxyRow, operation_id: str | None) -> None:
        self.operation_id = operation_id
        self.occurrences = 0
        self.statuses: list[int] = []
        self.query_params = row.query_params[:MAX_QUERY_PARAMS]

    def add(self, row: ProxyRow) -> None:
        self.occurrences += 1
        if (
            row.status is not None
            and row.status not in self.statuses
            and len(self.statuses) < MAX_STATUSES
        ):
            self.statuses.append(row.status)


type _Key = tuple[str, str, str]


def _build_finding(product: str, key: _Key, group: _Group) -> SignalFinding:
    method, template, category = key
    rule = RULE_BY_CATEGORY[category]
    fingerprint = signal_fingerprint(
        product=product, method=method, path_template=template, category=category
    )
    return SignalFinding(
        finding_id=f"S-{fingerprint[:8]}",
        fingerprint=fingerprint,
        category=rule.category,
        title=rule.label,
        proposed_severity=rule.severity,
        proposed_confidence=rule.confidence,
        cwe=rule.cwe,
        operation_id=group.operation_id,
        method=method,
        path_template=template,
        occurrences=group.occurrences,
        statuses=tuple(group.statuses),
        query_params=group.query_params,
    )


def _sort_key(key: _Key) -> tuple[int, str, str, str]:
    method, template, category = key
    return (-SEVERITY_RANK[RULE_BY_CATEGORY[category].severity], template, method, category)


def build_proxy_signals(
    rows: Sequence[ProxyRow],
    *,
    product: str,
    window: tuple[datetime, datetime],
    resolver: AlertResolver,
) -> ProxySignals:
    """Conta respostas lidas, não lidas e com sinal, e monta os achados.

    Só entram as linhas liberadas, com status, em `window` (inclusive). `examined` mais
    `skipped` é igual ao número dessas linhas. Um sinal nunca altera nenhuma decisão: este módulo
    só lê linhas já gravadas. Acima de `MAX_SIGNAL_FINDINGS` os achados de menor severidade
    ficam de fora (e contados em `findings_omitted`); as contagens seguem completas.
    """
    start, end = window
    seen = [
        row
        for row in rows
        if row.decision == "allow" and row.status is not None and start <= row.at <= end
    ]
    skipped = Counter(row.signal_skip for row in seen if row.signal_skip is not None)
    counts: Counter[str] = Counter()
    groups: dict[_Key, _Group] = {}
    with_signal = 0
    for row in seen:
        known = [name for name in dict.fromkeys(row.signals) if name in RULE_BY_CATEGORY]
        if not known or row.signal_skip is not None:
            continue
        with_signal += 1
        operation = resolver.resolve_path(row.method, row.path)
        template = (
            normalize_path_template(operation.path) if operation else generic_template(row.path)
        )
        for category in known:
            counts[category] += 1
            key = (row.method.upper(), template, category)
            if key not in groups:
                groups[key] = _Group(row, operation.operation_id if operation else None)
            groups[key].add(row)
    ordered = sorted(groups, key=_sort_key)
    return ProxySignals(
        enabled=True,
        window=SignalWindow(start=start.isoformat(), end=end.isoformat()),
        responses_examined=sum(1 for row in seen if row.signal_skip is None),
        responses_skipped=dict(sorted(skipped.items())),
        responses_with_signal=with_signal,
        counts={rule.category: counts.get(rule.category, 0) for rule in SIGNAL_RULES},
        findings=tuple(
            _build_finding(product, key, groups[key]) for key in ordered[:MAX_SIGNAL_FINDINGS]
        ),
        findings_omitted=max(len(ordered) - MAX_SIGNAL_FINDINGS, 0),
    )
