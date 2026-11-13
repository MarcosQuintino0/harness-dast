from datetime import UTC, datetime, timedelta

from harness_dast.adapters.system_clock import SystemClock


def test_now_returns_aware_utc_instant_close_to_the_real_time() -> None:
    before = datetime.now(UTC)

    instant = SystemClock().now()

    assert instant.utcoffset() == timedelta(0)
    assert before <= instant <= datetime.now(UTC)
