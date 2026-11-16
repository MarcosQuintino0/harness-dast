"""Contrato offline dos comandos de conhecimento."""

import json
from pathlib import Path

import pytest

from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import knowledge as commands
from tests.fakes.approvals import approve_product_on_disk
from tests.fakes.profile_data import dump_yaml, valid_profile_data

pytestmark = pytest.mark.contract


class _Zap:
    def version(self) -> str:
        return "2.17.0"

    def close(self) -> None:
        pass


def test_captura_e_diff_reconhecem_efeito_proposto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
                "info": {"title": "T", "version": "1"},
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
    approve_product_on_disk(tmp_path, "demo")
    monkeypatch.setattr(
        commands, "open_capture_zap", lambda *args: (_Zap(), "http://127.0.0.1:8080")
    )
    assert (
        run_app(
            build_app(), ["--json", "knowledge", "capture", "demo", "--products-dir", str(tmp_path)]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["data"]["activated"] is False
    (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")
    assert (
        run_app(
            build_app(), ["--json", "knowledge", "diff", "demo", "--products-dir", str(tmp_path)]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["data"]["reusable"] is False
    effect = next(item for item in result["data"]["entries"] if item["kind"] == "effect")
    assert "state" in effect["reasons"]
