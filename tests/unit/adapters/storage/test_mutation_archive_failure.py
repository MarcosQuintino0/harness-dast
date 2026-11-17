"""Falha de arquivamento do diario permanece bloqueada."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.domain.errors import ConfigError


def test_falha_ao_renomear_nao_reenvia_nem_libera(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = "a" * 64
    journal = FileMutationJournal(tmp_path)
    journal.begin(key, "unknown")
    target = tmp_path / f"{key}.jsonl"
    original = Path.rename

    def fail_archive(path: Path, destination: Path) -> Path:
        if path == target:
            raise OSError("falha injetada")
        return original(path, destination)

    monkeypatch.setattr(Path, "rename", fail_archive)
    with pytest.raises(ConfigError):
        journal.finish(key, "observed")
    lines = target.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[1])["outcome"] == "observed"
    with pytest.raises(ConfigError):
        journal.list_pending()
    with pytest.raises(ConfigError):
        journal.begin(key, "unknown")
    with pytest.raises(ConfigError):
        journal.release(key, datetime(2026, 1, 1, tzinfo=UTC))
