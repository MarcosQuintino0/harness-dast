"""Contratos públicos da estratégia sem rede nem alteração do perfil."""

import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.application.strategy import StrategyProfiles
from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy_basis import digest_strategy_document, make_strategy_basis
from tests.fakes.clock import FixedClock
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
    (directory / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "info": {"title": "Exemplo", "version": "1"},
                "paths": {
                    "/item": {
                        "get": {
                            "operationId": "listar",
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return directory


def _invoke(
    capsys: pytest.CaptureFixture[str], product: Path, *args: str
) -> tuple[int, dict[str, Any]]:
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
    if args[0] == "plan":
        assert result["data"]["executed"] is False
        assert result["data"]["preview"]["coverage"] == "pending_probe_and_zap"
        assert result["data"]["preview"]["operations"][0]["operation_id"] == "listar"
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


def test_previa_legada_e_estrategia_neutra_sao_iguais_sem_rede(
    product: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Tentativa de conexão na prévia")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    monkeypatch.setattr(socket, "create_connection", refuse_network)
    legacy_code, legacy = _invoke(capsys, product, "plan", "demo", "--dry-run")
    (product / "strategy.yml").write_text(STRATEGY, encoding="utf-8")

    strategy_code, strategy = _invoke(capsys, product, "plan", "demo", "--dry-run")

    assert legacy_code == strategy_code == 0
    assert legacy["data"]["executed"] is False
    assert strategy["data"]["executed"] is False
    assert legacy["data"]["preview"] == strategy["data"]["preview"]


@pytest.mark.parametrize(
    "factor",
    ["environment", "authorization", "accounts", "openapi", "data_rules", "flows", "planning"],
)
def test_drift_em_fontes_locais_fica_pendente_e_bloqueia_execucao(
    product: Path,
    capsys: pytest.CaptureFixture[str],
    factor: str,
) -> None:
    profile_data = valid_profile_data()
    basis = make_strategy_basis(
        ProductProfile.from_data(profile_data),
        openapi_sha256=digest_strategy_document((product / "openapi.json").read_bytes()),
        data_rules_sha256=digest_strategy_document((product / "data-rules.yml").read_bytes()),
        flows_sha256=digest_strategy_document((product / "flows.yml").read_bytes()),
        engine_version="2.17",
    )
    assert basis is not None
    strategy = yaml.safe_load(STRATEGY)
    strategy["choices"] = [
        {
            "name": "coverage",
            "value": "preserve",
            "source": "owner",
            "reason": "preserve_baseline",
            "state": "validated",
            "valid_until": "2999-12-31",
            "basis": basis.model_dump(),
        }
    ]
    (product / "strategy.yml").write_text(yaml.safe_dump(strategy), encoding="utf-8")
    initial_code, initial = _invoke(capsys, product, "strategy", "validate", "demo")
    assert initial_code == 0
    if factor == "environment":
        profile_data["environment"]["name"] = "outro"
    elif factor == "authorization":
        profile_data["scope"]["authorization"]["reference"] = "CHG-9999"
    elif factor == "accounts":
        profile_data["auth"]["accounts"][0]["role"] = "outro"
    elif factor == "planning":
        profile_data["probe"] = {"health_path": "/api/status"}
    else:
        filenames = {
            "openapi": "openapi.json",
            "data_rules": "data-rules.yml",
            "flows": "flows.yml",
        }
        path = product / filenames[factor]
        path.write_bytes(path.read_bytes() + b"\n")
    (product / "target.yml").write_text(dump_yaml(profile_data), encoding="utf-8")

    code, result = _invoke(capsys, product, "strategy", "validate", "demo")
    plan_code, plan = _invoke(capsys, product, "plan", "demo", "--dry-run")

    assert code == 0
    assert result["data"]["basis_context"][factor] != initial["data"]["basis_context"][factor]
    assert result["data"]["strategy_state"] == "review_required"
    assert result["data"]["basis_status"] == "engine_unavailable"
    assert plan_code == 2
    assert plan["error"]["code"] == "CONFIG_ERROR"
    profiles = StrategyProfiles(
        FileProfileRepository(product.parent),
        FileStrategyRepository(product.parent),
        FixedClock(datetime(2026, 11, 16, tzinfo=UTC)),
    )
    with pytest.raises(ConfigError):
        profiles.load("demo")
