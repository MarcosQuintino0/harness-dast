"""Preserva somente os parâmetros de coleta não secretos das integrações."""

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest

from tests.integration.lab_images import PREBUILT_MODE, build_session_images
from tests.integration.lab_support import REPO


@pytest.fixture(scope="session")
def _lab_prebuilt_images() -> dict[str, str]:
    """Prepara imagens uma vez por sessão de execução, quando solicitadas."""
    if os.environ.get(PREBUILT_MODE) != "1":
        return {}
    images = build_session_images(REPO, f"pytest-{uuid4().hex}", os.environ)
    return {PREBUILT_MODE: "1", **images}


@pytest.fixture(scope="session")
def _integration_measurement_settings(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, str | None]:
    return measurement_settings(tmp_path_factory)


def measurement_settings(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str | None]:
    """Captura os parâmetros de medição e reserva a pasta padrão da sessão."""
    settings = {
        key: os.environ.get(key)
        for key in ("HDAST_IT_METRICS_DIR", "HDAST_V17_DEADLINE_EPOCH", "HDAST_IT_STACK_SUFFIX")
    }
    if not settings["HDAST_IT_METRICS_DIR"]:
        settings["HDAST_IT_METRICS_DIR"] = str(tmp_path_factory.mktemp("integration-metrics"))
    return settings


@pytest.fixture(scope="module", autouse=True)
def _integration_module_metrics(
    _integration_measurement_settings: dict[str, str | None],
    _lab_prebuilt_images: dict[str, str],
) -> Iterator[None]:
    """Mantém métricas e imagens disponíveis no preparo e encerramento das pilhas."""
    metrics_dir = _integration_measurement_settings["HDAST_IT_METRICS_DIR"]
    assert metrics_dir is not None
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("HDAST_IT_METRICS_DIR", metrics_dir)
        for key, value in _lab_prebuilt_images.items():
            patch.setenv(key, value)
        yield


@pytest.fixture(autouse=True)
def _restore_integration_measurement_settings(
    _integration_measurement_settings: dict[str, str | None],
    _lab_prebuilt_images: dict[str, str],
    _isolate_hdast_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in {**_integration_measurement_settings, **_lab_prebuilt_images}.items():
        if value is not None:
            monkeypatch.setenv(key, value)
