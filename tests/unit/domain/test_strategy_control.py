"""Origem de controle local da captura não pode apontar para o alvo."""

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.strategy_control import ensure_capture_control_url


@pytest.mark.parametrize(
    "control", ["http://localhost:8090", "http://127.0.0.1:8090", "http://[::1]:8090"]
)
def test_aceita_origem_loopback_em_porta_distinta(control: str) -> None:
    ensure_capture_control_url(control, "http://localhost:8080")


@pytest.mark.parametrize(
    "control",
    [
        "http://localhost:8080",
        "http://127.0.0.2:8080",
        "http://[::1]:8080",
        "http://externo:8090",
        "http://segredo@localhost:8090",
        "http://localhost:8090/?segredo",
        "http://localhost:8090/#segredo",
        "http://localhost:8090/segredo",
        "http://localhost:99999",
    ],
)
def test_recusa_origem_insegura_sem_eco(control: str) -> None:
    with pytest.raises(ConfigError) as error:
        ensure_capture_control_url(control, "http://localhost:8080")
    assert "segredo" not in str(error.value)


def test_recusa_mesma_porta_padrao_em_loopback_equivalente() -> None:
    with pytest.raises(ConfigError):
        ensure_capture_control_url("http://localhost", "http://127.0.0.1:80")
