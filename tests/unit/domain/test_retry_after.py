"""Validação dos recuos pedidos por uma resposta remota."""

from datetime import UTC, datetime

import pytest

from harness_dast.domain.retry_after import retry_after_seconds

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10", 10),
        ("Mon, 16 Nov 2026 12:00:30 GMT", 30),
        (None, None),
        ("", None),
        ("-1", None),
        ("999", None),
        ("inf", None),
        ("0", None),
        ("Mon, 16 Nov 2026 12:00:30", None),
        ("\u0661", None),
    ],
)
def test_recuo_so_aceita_valor_acotado(value: str | None, expected: float | None) -> None:
    assert retry_after_seconds(value, NOW) == expected
