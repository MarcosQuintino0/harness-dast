"""Contrato independente da captura pública de vínculo, sem alvo nem Docker."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness_dast.adapters.http.target_client import HttpxTargetClient
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import strategy as commands
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy import Strategy
from harness_dast.domain.strategy_basis import digest_strategy_document, make_strategy_basis
from tests.fakes.approvals import approve_product_on_disk
from tests.fakes.profile_data import dump_yaml, valid_profile_data

pytestmark = pytest.mark.contract


class _Zap:
    def __init__(self, version: str = "2.17.0") -> None:
        self.value = version
        self.calls = 0
        self.closed = False
        self.fail = False
        self.on_version: Any = None

    def version(self) -> str:
        self.calls += 1
        if self.on_version is not None:
            self.on_version()
        if self.fail:
            raise ExternalToolError("motor indisponível")
        return self.value

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def setup_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, _Zap]:
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path / "state"))
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "target.yml").write_text(dump_yaml(valid_profile_data()), encoding="utf-8")
    (folder / "data-rules.yml").write_text("schema_version: 1\nrules: []\n", encoding="utf-8")
    (folder / "flows.yml").write_text("schema_version: 1\nbindings: []\n", encoding="utf-8")
    (folder / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "info": {"title": "segredo-sentinela", "version": "1"},
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
    zap = _Zap()
    monkeypatch.setattr(
        commands,
        "open_capture_zap",
        lambda product, products_dir, secrets: (zap, "http://127.0.0.1:8080"),
    )

    def reject_target(*args: object, **kwargs: object) -> None:
        raise AssertionError("Captura tentou enviar ao alvo")

    monkeypatch.setattr(HttpxTargetClient, "send", reject_target)
    return folder, zap


def _invoke(
    capsys: pytest.CaptureFixture[str], folder: Path, *args: str
) -> tuple[int, dict[str, Any]]:
    code = run_app(
        build_app(),
        ["--json", "strategy", "capture", "demo", *args, "--products-dir", str(folder.parent)],
    )
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("neutral", [False, True])
def test_captura_aprovada_gera_copia_tipificada_sem_ativacao(
    setup_capture: tuple[Path, _Zap],
    capsys: pytest.CaptureFixture[str],
    neutral: bool,
) -> None:
    folder, zap = setup_capture
    if neutral:
        (folder / "strategy.yml").write_text(
            "schema_version: 1\nreferences: {target: target.yml, "
            "data_rules: data-rules.yml, flows: flows.yml}\nchoices: []\n",
            encoding="utf-8",
        )
    approval = approve_product_on_disk(folder.parent, "demo")
    approval_file = folder.parent / "state" / "approvals" / "demo.json"
    approval_before = approval_file.read_bytes()
    before = {p.name: p.read_bytes() for p in folder.iterdir()}

    code, envelope = _invoke(capsys, folder)

    assert code == 0
    assert envelope == {
        "schema_version": 1,
        "ok": True,
        "data": {
            "product": "demo",
            "copy": "strategy.captured.yml",
            "changes": ["strategy_bound"],
            "classification": "automatic",
            "approval_changed": False,
            "activated": False,
        },
    }
    strategy = Strategy.from_data(
        yaml.safe_load((folder / "strategy.captured.yml").read_text(encoding="utf-8"))
    )
    choice = strategy.choices[0]
    assert "segredo-sentinela" not in (folder / "strategy.captured.yml").read_text(encoding="utf-8")
    assert "segredo-sentinela" not in json.dumps(envelope)
    assert (choice.name, choice.value, choice.source, choice.reason, choice.state) == (
        "coverage",
        "preserve",
        "observation",
        "preserve_baseline",
        "validated",
    )
    profile = ProductProfile.from_data(valid_profile_data())
    basis = make_strategy_basis(
        profile,
        openapi_sha256=digest_strategy_document((folder / "openapi.json").read_bytes()),
        data_rules_sha256=digest_strategy_document((folder / "data-rules.yml").read_bytes()),
        flows_sha256=digest_strategy_document((folder / "flows.yml").read_bytes()),
        engine_version="2.17.0",
    )
    assert choice.basis == basis
    assert choice.valid_until == profile.scope.authorization.valid_until
    assert {name: (folder / name).read_bytes() for name in before} == before
    assert approval_file.read_bytes() == approval_before
    assert approval.product == "demo"
    assert zap.calls == 1
    assert zap.closed is True


def _prepare_race(folder: Path, zap: _Zap, case: str) -> None:
    if case == "changed_doc":
        path = folder / "flows.yml"
        zap.on_version = lambda: path.write_bytes(path.read_bytes() + b"\n")
    elif case == "changed_profile":
        path = folder / "target.yml"
        altered = valid_profile_data()
        altered["environment"]["name"] = "outro"
        zap.on_version = lambda: path.write_text(dump_yaml(altered), encoding="utf-8")


def _prepare_refusal(folder: Path, zap: _Zap, case: str) -> None:
    destination = folder / "strategy.captured.yml"
    if case == "expired":
        expired = valid_profile_data()
        expired["scope"]["authorization"]["valid_until"] = "2000-01-01"
        (folder / "target.yml").write_text(dump_yaml(expired), encoding="utf-8")
    if case != "unapproved":
        approve_product_on_disk(folder.parent, "demo")
    if case == "document":
        (folder / "flows.yml").write_text("schema_version: [", encoding="utf-8")
    elif case == "existing_choice":
        (folder / "strategy.yml").write_text(
            "schema_version: 1\nreferences: {target: target.yml, "
            "data_rules: data-rules.yml, flows: flows.yml}\n"
            "choices: [{name: coverage, value: preserve, source: owner, "
            "reason: preserve_baseline, state: proposed, valid_until: '2999-12-31'}]\n",
            encoding="utf-8",
        )
    elif case == "invalid_engine":
        zap.value = "\x00segredo-sentinela"
    elif case == "unavailable":
        zap.fail = True
    elif case == "exists":
        destination.write_text("original", encoding="utf-8")
    elif case == "race":
        zap.on_version = lambda: destination.write_text("original", encoding="utf-8")
    _prepare_race(folder, zap, case)


@pytest.mark.parametrize(
    "case",
    [
        "unapproved",
        "document",
        "existing_choice",
        "invalid_engine",
        "unavailable",
        "unsafe",
        "exists",
        "race",
        "changed_doc",
        "changed_profile",
        "expired",
    ],
)
def test_captura_recusada_nao_cria_nem_sobrescreve(
    setup_capture: tuple[Path, _Zap],
    capsys: pytest.CaptureFixture[str],
    case: str,
) -> None:
    folder, zap = setup_capture
    destination = folder / "strategy.captured.yml"
    _prepare_refusal(folder, zap, case)

    code, envelope = _invoke(
        capsys, folder, *(["--output", "../strategy.x.yml"] if case == "unsafe" else [])
    )

    expected = (
        3
        if case in {"unapproved", "expired", "changed_profile"}
        else 5
        if case == "unavailable"
        else 2
    )
    assert code == expected
    assert envelope["ok"] is False
    assert "segredo-sentinela" not in json.dumps(envelope)
    if case in {"exists", "race"}:
        assert destination.read_text(encoding="utf-8") == "original"
    else:
        assert not destination.exists()
    if case in {"unapproved", "expired", "document", "existing_choice"}:
        assert zap.calls == 0
    assert zap.closed is True
