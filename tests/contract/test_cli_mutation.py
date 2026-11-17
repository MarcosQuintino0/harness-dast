"""Contrato de inspeção e recusa não interativa de mutações."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import typer

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.knowledge_mutation import MutationMetadata
from harness_dast.domain.mutation_snapshot import MutationSnapshot


def test_lista_pendencias_em_envelope_sem_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    FileMutationJournal(tmp_path / "mutations").begin("a" * 64, "unknown")
    assert run_app(build_app(), ["--json", "mutation", "list"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["data"]["pending"] == [{"id": "a" * 64, "metadata": None}]


def test_lista_so_os_metadados_permitidos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    metadata = MutationMetadata(
        operation_id="createItem",
        account="user_a",
        method="POST",
        run_id="run-1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    snapshot = MutationSnapshot(field="price", value=129.75, source="observed")
    FileMutationJournal(tmp_path / "mutations").begin("a" * 64, "present", snapshot, metadata)
    assert run_app(build_app(), ["--json", "mutation", "list"]) == 0
    text = capsys.readouterr().out
    item = json.loads(text)["data"]["pending"][0]
    assert item == {"id": "a" * 64, "metadata": metadata.model_dump(mode="json")}
    assert "snapshot" not in text
    assert "129.75" not in text


def test_release_recusa_json_e_preserva_pendencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    journal = FileMutationJournal(tmp_path / "mutations")
    journal.begin("a" * 64, "unknown")
    assert run_app(build_app(), ["--json", "mutation", "release", "a" * 64]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "CONFIG_ERROR"
    assert len(journal.list_pending()) == 1


def test_release_recusa_ausencia_de_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import harness_dast.cli.commands.mutation as command

    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(command, "is_interactive", lambda: False)
    journal = FileMutationJournal(tmp_path / "mutations")
    journal.begin("a" * 64, "unknown")
    assert run_app(build_app(), ["mutation", "release", "a" * 64]) == 2
    assert "terminal interativo" in capsys.readouterr().err
    assert len(journal.list_pending()) == 1


@pytest.mark.parametrize("args", [["mutation", "release"], ["mutation", "release", "../bad"]])
def test_release_recusa_id_ausente_ou_invalido_sem_pedir_confirmacao(
    args: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import harness_dast.cli.commands.mutation as command

    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(command, "is_interactive", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    asked: list[bool] = []

    def confirm(_: str) -> bool:
        asked.append(True)
        return False

    monkeypatch.setattr(command, "_confirm", confirm)
    journal = FileMutationJournal(tmp_path / "mutations")
    journal.begin("a" * 64, "unknown")
    assert run_app(build_app(), args) == 2
    assert asked == []
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


def test_release_interativo_confirma_por_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import harness_dast.cli.commands.mutation as command

    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    journal = FileMutationJournal(tmp_path / "mutations")
    journal.begin("a" * 64, "unknown")
    monkeypatch.setattr(command, "is_interactive", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(typer, "prompt", lambda *args, **kwargs: "a" * 64)
    assert run_app(build_app(), ["mutation", "release", "a" * 64]) == 0
    assert journal.list_pending() == ()
    assert "liberada" in capsys.readouterr().out
