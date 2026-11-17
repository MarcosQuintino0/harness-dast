"""Contrato de continuidade do contador de valores únicos no exchanges.json."""

import pytest
from pydantic import ValidationError

from harness_dast.domain.probe_exchange import ExchangeLog


@pytest.mark.parametrize("counter", [0, 1, 65536, None])
def test_counter_accepts_limits_and_legacy_absence(counter: int | None) -> None:
    log = ExchangeLog.model_validate(
        {"run_id": "run", "product": "app", "next_unique_counter": counter}
    )
    assert log.next_unique_counter == counter
    assert (
        ExchangeLog.model_validate({"run_id": "run", "product": "app"}).next_unique_counter is None
    )


@pytest.mark.parametrize("counter", [-1, 65537, True, "1", 1.5, {}, []])
def test_counter_rejects_invalid_external_value(counter: object) -> None:
    with pytest.raises(ValidationError):
        ExchangeLog.model_validate(
            {"run_id": "run", "product": "app", "next_unique_counter": counter}
        )
