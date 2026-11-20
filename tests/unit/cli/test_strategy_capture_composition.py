"""A captura usa somente controle publicado pela pilha gerenciada."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from harness_dast.cli import strategy_composition
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import strategy as strategy_commands
from harness_dast.domain.errors import ConfigError, StackBusy
from harness_dast.observability.logging import SecretRegistry


class _BusyLock:
    def __enter__(self) -> None:
        raise StackBusy("Pilha ocupada.")

    def __exit__(self, *_args: object) -> None:
        pass


def test_captura_recusa_pilha_ocupada_sem_consultar_controle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(strategy_commands, "hold_stack", lambda *_: _BusyLock())
    monkeypatch.setattr(
        strategy_commands,
        "open_capture_zap",
        lambda *_: pytest.fail("controle não deve ser aberto"),
    )

    assert (
        run_app(
            build_app(), ["--json", "strategy", "capture", "demo", "--products-dir", str(tmp_path)]
        )
        == 8
    )
    assert not (tmp_path / "demo" / "strategy.captured.yml").exists()


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
