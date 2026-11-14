from datetime import UTC, datetime
from pathlib import Path

import pytest

from harness_dast.adapters.storage.command_journal import FileCommandJournalStore
from harness_dast.domain.command_journal import JournalEntry
from harness_dast.domain.errors import ConfigError

T0 = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)


def _entry(command: str = "doctor") -> JournalEntry:
    return JournalEntry(
        started_at=T0, finished_at=T0, command=command, exit_code=0, state="ok", product="clinica"
    )


def test_append_e_load_devolvem_as_linhas_na_ordem(tmp_path: Path) -> None:
    store = FileCommandJournalStore(tmp_path)

    store.append("clinica", _entry("doctor"))
    store.append("clinica", _entry("probe"))

    loaded = store.load("clinica")
    assert [e.command for e in loaded.entries] == ["doctor", "probe"]
    assert loaded.skipped_lines == 0


def test_load_de_diario_inexistente_devolve_vazio(tmp_path: Path) -> None:
    loaded = FileCommandJournalStore(tmp_path).load("clinica")

    assert (loaded.entries, loaded.skipped_lines) == ((), 0)


def test_load_pula_linha_corrompida_e_conta(tmp_path: Path) -> None:
    store = FileCommandJournalStore(tmp_path)
    store.append("clinica", _entry())
    with store.location("clinica").open("ab") as handle:
        handle.write(b"{corrompido\n\xff\xfe\n")
    store.append("clinica", _entry("probe"))

    loaded = store.load("clinica")

    assert [e.command for e in loaded.entries] == ["doctor", "probe"]
    assert loaded.skipped_lines == 2


def test_diario_fica_em_pasta_journal_por_produto(tmp_path: Path) -> None:
    store = FileCommandJournalStore(tmp_path)

    store.append("clinica", _entry())
    store.append(None, _entry("version"))

    assert (tmp_path / "journal" / "clinica.jsonl").is_file()
    assert (tmp_path / "journal" / "_sem-produto.jsonl").is_file()


def test_produto_com_caminho_nao_escapa_da_pasta(tmp_path: Path) -> None:
    store = FileCommandJournalStore(tmp_path / "estado")

    store.append("../../fora", _entry())

    assert not (tmp_path / "fora.jsonl").exists()
    assert (tmp_path / "estado" / "journal" / "_sem-produto.jsonl").is_file()


def test_append_em_pasta_impossivel_levanta_config_error(tmp_path: Path) -> None:
    blocker = tmp_path / "arquivo"
    blocker.write_text("x", encoding="utf-8")
    store = FileCommandJournalStore(blocker)

    with pytest.raises(ConfigError):
        store.append("clinica", _entry())


def test_cada_linha_do_arquivo_traz_schema_version(tmp_path: Path) -> None:
    store = FileCommandJournalStore(tmp_path)
    store.append("clinica", _entry())

    line = store.location("clinica").read_text(encoding="utf-8").splitlines()[0]

    assert '"schema_version":1' in line
