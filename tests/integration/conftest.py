"""Preserva somente os parâmetros de coleta não secretos das integrações."""

import os

import pytest


@pytest.fixture(scope="module")
def _integration_measurement_settings() -> dict[str, str | None]:
    return {
        key: os.environ.get(key)
        for key in ("HDAST_IT_METRICS_DIR", "HDAST_V17_DEADLINE_EPOCH", "HDAST_IT_STACK_SUFFIX")
    }


@pytest.fixture(autouse=True)
def _restore_integration_measurement_settings(
    _integration_measurement_settings: dict[str, str | None],
    _isolate_hdast_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in _integration_measurement_settings.items():
        if value is not None:
            monkeypatch.setenv(key, value)
