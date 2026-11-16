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
    assert result["data"]["reusable"] is False  # sem --run, tudo é proposta: nada a reutilizar
    effect = next(item for item in result["data"]["entries"] if item["kind"] == "effect")
    assert "state" in effect["reasons"]


def test_captura_cli_com_run_valido_e_recusa_run_ausente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from harness_dast.adapters.storage.product_documents import FileProductDocuments
    from harness_dast.application.probe import ProbeRequest
    from harness_dast.domain.probe_result import OperationResult
    from harness_dast.domain.profile import ProductProfile
    from tests.fakes.rig import Rig

    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HDAST_RUNS_DIR", str(tmp_path / "runs"))
    folder = tmp_path / "demo"
    folder.mkdir()
    raw = valid_profile_data()
    (folder / "target.yml").write_text(dump_yaml(raw), encoding="utf-8")
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
    rig = Rig()
    sample = rig.probe().execute(ProbeRequest(product="agenda", only=("listar",)))
    profile = ProductProfile.from_data(raw)
    account = profile.auth.accounts[0].alias
    operation = OperationResult(
        operation_id="listar",
        method="GET",
        path="/item",
        outcome="success",
        status=200,
        account=account,
        attempts=1,
    )
    probe = sample.model_copy(update={"product": "demo", "operations": (operation,)})
    run_id = sample.run_id
    manifest = rig.store.manifests[run_id][-1].model_copy(
        update={
            "product": "demo",
            "accounts": (account,),
            "hashes": FileProductDocuments(tmp_path).hashes("demo", profile),
        }
    )
    path = tmp_path / "runs" / run_id
    path.mkdir(parents=True)
    (path / "probe.json").write_text(probe.model_dump_json(), encoding="utf-8")
    (path / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    code = run_app(
        build_app(),
        [
            "--json",
            "knowledge",
            "capture",
            "demo",
            "--run",
            run_id,
            "--products-dir",
            str(tmp_path),
        ],
    )
    data = json.loads(capsys.readouterr().out)
    assert code == 0, data
    import yaml

    knowledge = yaml.safe_load((folder / "knowledge.captured.yml").read_text(encoding="utf-8"))
    assert knowledge["observed_accounts"] == [account]
    assert knowledge["provenance"]["run_id"] == run_id
    (folder / "knowledge.captured.yml").unlink()
    (path / "probe.json").unlink()
    code = run_app(
        build_app(),
        [
            "--json",
            "knowledge",
            "capture",
            "demo",
            "--run",
            run_id,
            "--products-dir",
            str(tmp_path),
        ],
    )
    assert code == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert not (folder / "knowledge.captured.yml").exists()
