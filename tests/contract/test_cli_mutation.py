"""Contrato de inspeção e recusa não interativa de mutações."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.cli.app import build_app, run_app


def test_lista_pendencias_em_envelope_sem_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    FileMutationJournal(tmp_path / "mutations").begin("a" * 64, "unknown")
    assert run_app(build_app(), ["--json", "mutation", "list"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["data"]["pending"] == [{"id": "a" * 64, "metadata": None}]


def test_release_recusa_json_e_preserva_pendencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    journal = FileMutationJournal(tmp_path / "mutations")
    journal.begin("a" * 64, "unknown")
    assert run_app(build_app(), ["--json", "mutation", "release", "a" * 64]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "CONFIG_ERROR"
    assert len(journal.list_pending()) == 1


def test_lista_recusa_diario_corrompido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    directory = tmp_path / "mutations"
    directory.mkdir()
    (directory / ("a" * 64 + ".jsonl")).write_text("segredo-malformado", encoding="utf-8")
    assert run_app(build_app(), ["--json", "mutation", "list"]) == 2
    assert "segredo-malformado" not in capsys.readouterr().out
