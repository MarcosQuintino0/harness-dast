"""Testes independentes (QA) das configurações lidas do ambiente."""

# ruff: noqa: S105, S104, S603, RUF001, RUF100, PT011, TRY301

import json
from pathlib import Path

import pytest

from harness_dast.config.settings import Settings, load_settings
from harness_dast.domain.errors import ConfigError

KEY = "chave-zap-SUPERSECRETA-987"
NAMES = (
    "HDAST_ZAP_BASE_URL",
    "HDAST_ZAP_API_KEY",
    "HDAST_RUNS_DIR",
    "HDAST_PRODUCTS_DIR",
    "HDAST_LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    # Isola de um .env real no diretório de trabalho.
    monkeypatch.chdir(tmp_path)


def test_load_settings_returns_documented_defaults_when_environment_is_empty() -> None:
    settings = load_settings()

    assert settings.zap_base_url == "http://127.0.0.1:8080"
    assert settings.zap_api_key is None
    assert settings.runs_dir == Path("runs")
    assert settings.products_dir == Path("products")
    assert settings.log_level == "INFO"


def test_load_settings_reads_every_variable_when_all_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HDAST_ZAP_BASE_URL", "http://zap:8090")
    monkeypatch.setenv("HDAST_ZAP_API_KEY", KEY)
    monkeypatch.setenv("HDAST_RUNS_DIR", "saida")
    monkeypatch.setenv("HDAST_PRODUCTS_DIR", "../perfis")
    monkeypatch.setenv("HDAST_LOG_LEVEL", "DEBUG")

    settings = load_settings()

    assert settings.zap_base_url == "http://zap:8090"
    assert settings.zap_api_key is not None
    assert settings.zap_api_key.get_secret_value() == KEY
    assert settings.runs_dir == Path("saida")
    assert settings.log_level == "DEBUG"


def test_api_key_never_appears_in_repr_str_or_dumps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HDAST_ZAP_API_KEY", KEY)

    settings = load_settings()

    for text in (
        repr(settings),
        str(settings),
        settings.model_dump_json(),
        json.dumps(settings.model_dump(mode="json")),
        str(settings.model_dump()),
        repr(settings.zap_api_key),
        f"{settings}",
        f"{settings!r}",
        str(settings.model_dump(mode="python")),
    ):
        assert KEY not in text


@pytest.mark.parametrize(
    "name",
    [
        "HDAST_LOG_LEVEL",
    ],
)
@pytest.mark.parametrize("value", ["", "info", "TRACE", "CRITICAL", "NADA", "1", " INFO", "INFO "])
def test_load_settings_raises_config_error_when_log_level_is_invalid(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigError) as caught:
        load_settings()

    assert name in caught.value.message
    assert value.strip() == "" or value not in caught.value.message or value in name


def test_load_settings_error_never_contains_the_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HDAST_LOG_LEVEL", "VALOR-SECRETO-XYZ")
    monkeypatch.setenv("HDAST_ZAP_API_KEY", KEY)

    with pytest.raises(ConfigError) as caught:
        load_settings()

    blob = f"{caught.value.message}|{caught.value.hint}|{caught.value}"
    assert "VALOR-SECRETO-XYZ" not in blob
    assert KEY not in blob


def test_load_settings_exception_chain_does_not_expose_the_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `raise ... from exc` preserva o ValidationError original, cujo texto repete o valor.
    # A CLI imprime só message/hint, mas qualquer log do traceback encadeado vazaria.
    monkeypatch.setenv("HDAST_LOG_LEVEL", "VALOR-SECRETO-XYZ")

    with pytest.raises(ConfigError) as caught:
        load_settings()

    cause = caught.value.__cause__
    assert cause is None or "VALOR-SECRETO-XYZ" not in str(cause)


def test_load_settings_ignores_unrelated_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HDAST_NAO_EXISTE", "x")
    monkeypatch.setenv("OUTRA_COISA", "y")

    assert load_settings().log_level == "INFO"


def test_settings_is_immutable() -> None:
    settings = Settings()

    with pytest.raises(ValueError):
        settings.log_level = "DEBUG"  # type: ignore[misc]  # prova da imutabilidade


def test_load_settings_does_not_read_dotenv_file_from_working_directory(
    tmp_path: Path,
) -> None:
    # O .env guarda segredos; a ferramenta só lê o ambiente do processo (variáveis HDAST_*).
    (tmp_path / ".env").write_text(f"HDAST_ZAP_API_KEY={KEY}\n", encoding="utf-8")

    assert load_settings().zap_api_key is None


def test_load_settings_accepts_empty_api_key_as_a_value_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HDAST_ZAP_API_KEY", "")

    settings = load_settings()

    assert settings.zap_api_key is None or settings.zap_api_key.get_secret_value() == ""


def test_load_settings_rejects_zap_url_that_is_not_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HDAST_ZAP_BASE_URL", "file:///etc/passwd")

    with pytest.raises(ConfigError):
        load_settings()
