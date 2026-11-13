"""`domain.traffic`: resumo do tráfego do proxy durante o scan."""

from datetime import UTC, datetime, timedelta

from harness_dast.domain.traffic import ProxyRow, summarize_traffic

T0 = datetime(2026, 11, 13, 10, 0, 0, tzinfo=UTC)


def row(
    offset: float, decision: str = "allow", reason: str = "allowed", method: str = "GET"
) -> ProxyRow:
    return ProxyRow(
        at=T0 + timedelta(seconds=offset), decision=decision, reason=reason, method=method
    )


def test_summary_counts_allowed_denied_and_reasons() -> None:
    rows = [
        row(0),
        row(1, "deny", "path_not_allowed"),
        row(2, "deny", "malformed_request"),
        row(3, "deny", "malformed_request"),
        row(4, method="POST"),
    ]

    summary = summarize_traffic(rows, start=T0, end=T0 + timedelta(seconds=10), limit_rps=5)

    assert (summary.allowed, summary.denied) == (2, 3)
    assert summary.denied_by_reason == {"path_not_allowed": 1, "malformed_request": 2}
    assert summary.allowed_by_method == {"GET": 1, "POST": 1}
    assert summary.enabled is True


def test_summary_ignores_rows_outside_the_interval() -> None:
    rows = [row(-5), row(1), row(50)]

    summary = summarize_traffic(rows, start=T0, end=T0 + timedelta(seconds=10), limit_rps=5)

    assert summary.allowed == 1


def test_summary_computes_average_and_peak_rate() -> None:
    rows = [row(0.0), row(0.2), row(0.4), row(0.6), row(2.0)]

    summary = summarize_traffic(rows, start=T0, end=T0 + timedelta(seconds=10), limit_rps=5)

    assert summary.peak_rps == 4
    assert summary.duration_seconds == 2.0
    assert summary.average_rps == 2.5
    assert summary.limit_rps == 5


def test_summary_of_nothing_is_zero_but_enabled() -> None:
    summary = summarize_traffic([], start=T0, end=T0, limit_rps=5)

    assert (summary.allowed, summary.denied, summary.peak_rps, summary.average_rps) == (0, 0, 0, 0)
    assert summary.enabled is True
