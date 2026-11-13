from pathlib import Path

import pytest

from harness_dast.config.settings import load_settings
from harness_dast.domain.errors import ConfigError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "HDAST_ZAP_BASE_URL",
        "HDAST_ZAP_API_KEY",
        "HDAST_RUNS_DIR",
        "HDAST_PRODUCTS_DIR",
        "HDAST_LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_used_when_environment_is_empty() -> None:
    settings = load_settings()

    assert settings.zap_base_url == "http://127.0.0.1:8080"
    assert settings.zap_api_key is None
    assert settings.runs_dir == Path("runs")
    assert settings.products_dir == Path("products")
    assert settings.log_level == "INFO"


def test_values_are_read_when_variables_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HDAST_ZAP_BASE_URL", "http://zap:9090")
    monkeypatch.setenv("HDAST_ZAP_API_KEY", "chave-de-teste")
    monkeypatch.setenv("HDAST_RUNS_DIR", "saida")
    monkeypatch.setenv("HDAST_LOG_LEVEL", "DEBUG")

    settings = load_settings()

    assert settings.zap_base_url == "http://zap:9090"
    assert settings.zap_api_key is not None
    assert settings.zap_api_key.get_secret_value() == "chave-de-teste"
    assert settings.runs_dir == Path("saida")
    assert settings.log_level == "DEBUG"


def test_api_key_is_hidden_when_settings_are_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HDAST_ZAP_API_KEY", "chave-de-teste")

    assert "chave-de-teste" not in repr(load_settings())


def test_config_error_names_variable_but_not_value_when_log_level_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HDAST_LOG_LEVEL", "VALOR-INVALIDO")

    with pytest.raises(ConfigError) as info:
        load_settings()

    assert "HDAST_LOG_LEVEL" in info.value.message
    assert "VALOR-INVALIDO" not in info.value.message
    assert info.value.hint is not None


def test_unrelated_variables_are_ignored_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HDAST_NAO_EXISTE", "x")

    assert load_settings().log_level == "INFO"
