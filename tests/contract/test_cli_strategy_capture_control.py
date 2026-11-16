"""Contrato do controle da pilha gerenciada durante a captura."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness_dast.cli import strategy_composition
from harness_dast.cli.commands import strategy as commands
from harness_dast.cli.stack_lock_composition import hold_stack
from tests.contract.test_cli_strategy_capture import _invoke, _Zap
from tests.contract.test_cli_strategy_capture import setup_capture as setup_capture
from tests.fakes.approvals import approve_product_on_disk
from tests.fakes.profile_data import dump_yaml, valid_profile_data

pytestmark = pytest.mark.contract


def test_captura_respeita_trava_ocupada_e_prossegue_depois_de_liberada(
    setup_capture: tuple[Path, _Zap],
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder, zap = setup_capture
    approve_product_on_disk(folder.parent, "demo")

    with hold_stack("teste", "demo"):
        code, envelope = _invoke(capsys, folder)
        assert code == 8
        assert envelope["error"]["code"] == "STACK_BUSY"
        assert zap.calls == 0
        assert not (folder / "strategy.captured.yml").exists()

    code, envelope = _invoke(capsys, folder)
    assert code == 0
    assert envelope["ok"] is True
    assert zap.calls == 1


def test_captura_libera_trava_quando_motor_falha(
    setup_capture: tuple[Path, _Zap],
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder, zap = setup_capture
    approve_product_on_disk(folder.parent, "demo")
    zap.fail = True

    failed, _ = _invoke(capsys, folder)
    zap.fail = False
    retried, result = _invoke(capsys, folder)

    assert failed == 5
    assert retried == 0
    assert result["ok"] is True


@pytest.mark.parametrize(
    ("control_url", "target_url"),
    [
        ("http://127.0.0.1:8080", "http://localhost:8080"),
        ("http://localhost:8080", "http://127.0.0.1:8080"),
        ("http://[::1]:8080", "http://127.0.0.1:8080"),
        ("http://remote.example:8080", "https://api.hml.acme-teste.net.br"),
        ("http://user:secret@127.0.0.1:8080", "https://api.hml.acme-teste.net.br"),
    ],
)
def test_captura_recusa_controle_inseguro_antes_de_consultar_motor(
    setup_capture: tuple[Path, _Zap],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    control_url: str,
    target_url: str,
) -> None:
    folder, zap = setup_capture
    data = valid_profile_data()
    data["environment"]["base_url"] = target_url
    if target_url.startswith("http://"):
        from urllib.parse import urlsplit

        data["scope"]["allow"][0].update(
            {
                "host": urlsplit(target_url).hostname,
                "scheme": "http",
                "port": 8080,
                "allow_local": True,
            }
        )
    (folder / "target.yml").write_text(dump_yaml(data), encoding="utf-8")
    approve_product_on_disk(folder.parent, "demo")
    monkeypatch.setattr(
        commands, "open_capture_zap", lambda product, products_dir, secrets: (zap, control_url)
    )

    code, envelope = _invoke(capsys, folder)

    assert code == 2
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert "secret" not in json.dumps(envelope)
    assert zap.calls == 0
    assert zap.closed is True
    assert not (folder / "strategy.captured.yml").exists()


@pytest.mark.parametrize("case", ["absent", "wrong_product", "wrong_run", "stopped", "override"])
def test_capture_cli_exige_pilha_certa_e_ignora_override(
    setup_capture: tuple[Path, _Zap],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    folder, zap = setup_capture
    approve_product_on_disk(folder.parent, "demo")
    url = "http://127.0.0.1:8080"
    report = SimpleNamespace(
        managed=True,
        running=True,
        kill_switch=False,
        product="demo",
        run_id="execucao",
        zap_url=url,
    )
    state: SimpleNamespace | None = SimpleNamespace(
        product="demo", run_id="execucao", zap_url=url, zap_api_key="chave-sintetica"
    )
    if case == "absent":
        state = None
    elif case == "wrong_product":
        report.product = "outro"
    elif case == "wrong_run":
        report.run_id = "outra-execucao"
    elif case == "stopped":
        report.kill_switch = True
    monkeypatch.setenv("HDAST_ZAP_BASE_URL", "http://api.hml.acme-teste.net.br")
    monkeypatch.setattr(commands, "open_capture_zap", strategy_composition.open_capture_zap)
    monkeypatch.setattr(
        strategy_composition,
        "build_stack_manager",
        lambda _: SimpleNamespace(status=lambda: report),
    )
    monkeypatch.setattr(
        strategy_composition, "open_state_store", lambda: SimpleNamespace(load=lambda: state)
    )
    used: list[str] = []

    def make_client(address: str, key: str) -> _Zap:
        used.append(address)
        return zap

    monkeypatch.setattr(strategy_composition, "ZapApiClient", make_client)
    code, envelope = _invoke(capsys, folder)

    if case == "override":
        assert code == 0
        assert envelope["ok"] is True
        assert used == [url]
        assert zap.calls == 1
    else:
        assert code == 2
        assert envelope["error"]["code"] == "CONFIG_ERROR"
        assert used == []
        assert zap.calls == 0
        assert not (folder / "strategy.captured.yml").exists()
