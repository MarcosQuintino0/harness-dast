"""Testes do diário de intenções e resultados desconhecidos."""

from pathlib import Path

import pytest

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.domain.errors import ConfigError


def test_intencao_pendente_bloqueia_nova_tentativa(tmp_path: Path) -> None:
    key = "a" * 64
    journal = FileMutationJournal(tmp_path)
    journal.begin(key, "unknown")
    with pytest.raises(ConfigError):
        FileMutationJournal(tmp_path).begin(key, "unknown")
    assert '"previous_state": "unknown"' in (tmp_path / (key + ".jsonl")).read_text()


def test_resultado_conhecido_permite_nova_tentativa(tmp_path: Path) -> None:
    key = "b" * 64
    journal = FileMutationJournal(tmp_path)
    journal.begin(key, "absent")
    journal.finish(key, "succeeded")
    journal.begin(key, "present")
    assert len(list((tmp_path / "completed").iterdir())) == 1


def test_pendente_corrompido_bloqueia_repeticao(tmp_path: Path) -> None:
    key = "c" * 64
    (tmp_path / (key + ".jsonl")).write_text("{")
    journal = FileMutationJournal(tmp_path)
    with pytest.raises(ConfigError):
        journal.finish(key, "succeeded")
    with pytest.raises(ConfigError):
        journal.begin(key, "unknown")


@pytest.mark.parametrize("key", ["", "../a", "A" * 64])
def test_chave_invalida_recusada(tmp_path: Path, key: str) -> None:
    with pytest.raises(ConfigError):
        FileMutationJournal(tmp_path).begin(key, "unknown")
