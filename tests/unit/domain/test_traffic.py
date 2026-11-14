"""`domain.traffic`: resumo do tráfego do proxy durante o scan."""

from datetime import UTC, datetime, timedelta

from harness_dast.domain.traffic import ProxyRow, find_gaps, summarize_traffic

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


# ------------------------------------------------------------------ lacunas (ADR 0031)


def test_gaps_count_only_the_silences_longer_than_the_threshold_between_two_requests() -> None:
    rows = [row(0), row(3), row(30), row(31, "deny"), row(60)]

    gaps = find_gaps(rows, start=T0, end=T0 + timedelta(seconds=100))

    assert gaps.count == 2
    assert gaps.total_seconds == 56.0
    assert gaps.longest_seconds == 29.0


def test_a_silence_equal_to_the_threshold_is_not_a_gap() -> None:
    gaps = find_gaps([row(0), row(10)], start=T0, end=T0 + timedelta(seconds=20))

    assert gaps.count == 0


def test_time_before_the_first_and_after_the_last_request_is_not_a_gap() -> None:
    gaps = find_gaps([row(50), row(51)], start=T0, end=T0 + timedelta(seconds=500))

    assert gaps.count == 0
    assert gaps.longest_seconds == 0.0


def test_gaps_ignore_rows_outside_the_interval_and_unsorted_input() -> None:
    rows = [row(200), row(40), row(0), row(-100)]

    gaps = find_gaps(rows, start=T0, end=T0 + timedelta(seconds=100))

    assert (gaps.count, gaps.total_seconds) == (1, 40.0)


def test_no_rows_or_one_row_means_no_gaps() -> None:
    assert find_gaps([], start=T0, end=T0 + timedelta(seconds=10)).count == 0
    assert find_gaps([row(1)], start=T0, end=T0 + timedelta(seconds=10)).count == 0


def test_the_threshold_can_be_changed() -> None:
    gaps = find_gaps(
        [row(0), row(4)], start=T0, end=T0 + timedelta(seconds=10), threshold_seconds=2.0
    )

    assert (gaps.count, gaps.threshold_seconds) == (1, 2.0)
