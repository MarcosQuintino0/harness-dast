"""A captura usa somente controle publicado pela pilha gerenciada."""

from types import SimpleNamespace

import pytest

from harness_dast.cli import strategy_composition
from harness_dast.domain.errors import ConfigError
from harness_dast.observability.logging import SecretRegistry


def test_captura_recusa_sem_pilha_antes_de_criar_cliente(monkeypatch: pytest.MonkeyPatch) -> None:
    report = SimpleNamespace(managed=False, running=False, kill_switch=False)
    monkeypatch.setattr(
        strategy_composition,
        "build_stack_manager",
        lambda _: SimpleNamespace(status=lambda: report),
    )
    monkeypatch.setattr(
        strategy_composition, "open_state_store", lambda: SimpleNamespace(load=lambda: None)
    )
    monkeypatch.setattr(
        strategy_composition, "ZapApiClient", lambda *_: pytest.fail("cliente não deve ser criado")
    )

    with pytest.raises(ConfigError):
        strategy_composition.open_capture_zap("demo", None, SecretRegistry())


def test_captura_usa_endpoint_publicado_pela_pilha(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "http://127.0.0.1:8080"
    report = SimpleNamespace(
        managed=True,
        running=True,
        kill_switch=False,
        product="demo",
        run_id="execucao",
        zap_url=url,
    )
    state = SimpleNamespace(
        product="demo", run_id="execucao", zap_url=url, zap_api_key="chave-sintetica"
    )
    monkeypatch.setattr(
        strategy_composition,
        "build_stack_manager",
        lambda _: SimpleNamespace(status=lambda: report),
    )
    monkeypatch.setattr(
        strategy_composition, "open_state_store", lambda: SimpleNamespace(load=lambda: state)
    )
    seen: list[str] = []
    monkeypatch.setattr(
        strategy_composition, "ZapApiClient", lambda address, key: seen.append(address)
    )
    monkeypatch.setenv("HDAST_ZAP_BASE_URL", "http://127.0.0.1:9999")

    _, observed_url = strategy_composition.open_capture_zap("demo", None, SecretRegistry())

    assert observed_url == url
    assert seen == [url]
