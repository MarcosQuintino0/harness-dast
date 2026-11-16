"""Contratos públicos da estratégia sem rede nem alteração do perfil."""

import json
import socket
from pathlib import Path

import pytest

from harness_dast.cli.app import build_app, run_app
from tests.fakes.profile_data import dump_yaml, valid_profile_data

pytestmark = pytest.mark.contract

STRATEGY = """schema_version: 1
references:
  target: target.yml
  data_rules: data-rules.yml
  flows: flows.yml
choices: []
"""


@pytest.fixture
def product(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path / "state"))
    directory = tmp_path / "demo"
    directory.mkdir()
    (directory / "target.yml").write_text(dump_yaml(valid_profile_data()), encoding="utf-8")
    (directory / "data-rules.yml").write_text("schema_version: 1\nrules: []\n", encoding="utf-8")
    (directory / "flows.yml").write_text("schema_version: 1\nbindings: []\n", encoding="utf-8")
    return directory


def _invoke(capsys: pytest.CaptureFixture[str], product: Path, *args: str) -> tuple[int, dict]:
    code = run_app(build_app(), ["--json", *args, "--products-dir", str(product.parent)])
    captured = capsys.readouterr()
    return code, json.loads(captured.out)


@pytest.mark.parametrize(
    "args",
    [("strategy", "validate", "demo"), ("strategy", "diff", "demo"), ("plan", "demo", "--dry-run")],
)
def test_consultas_locais_nao_abrem_rede_nem_alteram_arquivos(
    product: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    args: tuple[str, ...],
) -> None:
    (product / "strategy.yml").write_text(STRATEGY, encoding="utf-8")
    before = {p.name: p.read_bytes() for p in product.iterdir()}

    def refuse_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Tentativa de conexão durante consulta local")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    monkeypatch.setattr(socket, "create_connection", refuse_network)
    code, result = _invoke(capsys, product, *args)

    assert code == 0
    assert result["schema_version"] == 1
    assert result["ok"] is True
    assert result["data"]["approval_state"] != "approved"
    assert {p.name: p.read_bytes() for p in product.iterdir()} == before


@pytest.mark.parametrize(
    "content",
    [
        "schema_version: [",
        "{}",
        STRATEGY + "secret-key: sentinel-secret\n",
        STRATEGY.replace("schema_version: 1", "schema_version: .nan"),
        STRATEGY.replace("schema_version: 1", "schema_version: .inf"),
        STRATEGY.replace("target: target.yml", "target: ../target.yml"),
        STRATEGY.replace("choices: []", "choices: &cycle [*cycle]"),
    ],
)
def test_estrategia_invalida_recusada_sem_ecoar_valores(
    product: Path,
    capsys: pytest.CaptureFixture[str],
    content: str,
) -> None:
    (product / "strategy.yml").write_text(content, encoding="utf-8")

    code, result = _invoke(capsys, product, "strategy", "validate", "demo")

    assert code == 2
    assert result["ok"] is False
    assert result["error"]["code"] == "CONFIG_ERROR"
    assert "sentinel-secret" not in json.dumps(result)


def test_migracao_produz_copia_sem_alterar_perfil_ou_aprovacao(
    product: Path,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    before = {p.name: p.read_bytes() for p in product.iterdir()}

    code, result = _invoke(capsys, product, "strategy", "migrate", "demo")

    assert code == 0
    assert result["ok"] is True
    assert result["data"]["approval_changed"] is False
    assert (product / result["data"]["copy"]).is_file()
    assert {name: (product / name).read_bytes() for name in before} == before
    assert not list((tmp_path / "state").rglob("approvals/*"))


def test_migracao_de_estrategia_existente_nao_descarta_escolhas(
    product: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = product / "strategy.yml"
    original.write_text(STRATEGY, encoding="utf-8")

    code, result = _invoke(capsys, product, "strategy", "migrate", "demo")

    assert code == 2
    assert result["error"]["code"] == "CONFIG_ERROR"
    assert original.read_text(encoding="utf-8") == STRATEGY
    assert not (product / "strategy.migrated.yml").exists()
