"""Contratos de inspeção e recuperação humana do diário."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.application.mutation_release import release_mutation
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge_mutation import MutationMetadata, MutationPending

KEY = "a" * 64
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_lista_metadados_e_preserva_legado(tmp_path: Path) -> None:
    journal = FileMutationJournal(tmp_path)
    metadata = MutationMetadata(
        operation_id="createItem", account="user_a", method="POST", run_id="run-1", started_at=NOW
    )
    journal.begin(KEY, "unknown", metadata=metadata)
    journal.begin("b" * 64, "unknown")
    pending = journal.list_pending()
    assert pending[0].metadata == metadata
    assert pending[1].metadata is None


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{",
        '{"intent":"mutation"}',
        '{"intent":"mutation","intent":"mutation","previous_state":"unknown"}',
    ],
)
def test_recusa_registro_malformado_sem_expor_conteudo(tmp_path: Path, content: str) -> None:
    (tmp_path / (KEY + ".jsonl")).write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError):
        FileMutationJournal(tmp_path).list_pending()
    with pytest.raises(ConfigError) as error:
        FileMutationJournal(tmp_path).begin(KEY, "unknown")
    assert not isinstance(error.value, MutationPending)


@pytest.mark.parametrize("metadata", [None, {}, {"operation_id": "read"}, "invalid"])
def test_recusa_metadados_malformados(tmp_path: Path, metadata: object) -> None:
    entry = {"intent": "mutation", "previous_state": "unknown", "metadata": metadata}
    (tmp_path / (KEY + ".jsonl")).write_text(json.dumps(entry), encoding="utf-8")
    with pytest.raises(ConfigError):
        FileMutationJournal(tmp_path).list_pending()


def test_pendencia_valida_tem_excecao_propria(tmp_path: Path) -> None:
    journal = FileMutationJournal(tmp_path)
    journal.begin(KEY, "unknown")
    with pytest.raises(MutationPending):
        journal.begin(KEY, "unknown")


def test_recusa_sem_terminal_e_nao_libera(tmp_path: Path) -> None:
    journal = FileMutationJournal(tmp_path)
    journal.begin(KEY, "unknown")
    with pytest.raises(ConfigError):
        release_mutation(journal, KEY, interactive=False, confirm=lambda _: True, now=lambda: NOW)
    assert len(journal.list_pending()) == 1


def test_libera_com_confirmacao_e_registra_auditoria(tmp_path: Path) -> None:
    journal = FileMutationJournal(tmp_path)
    journal.begin(KEY, "unknown")
    assert release_mutation(journal, KEY, interactive=True, confirm=lambda _: True, now=lambda: NOW)
    assert journal.list_pending() == ()
    archive = next((tmp_path / "completed").iterdir())
    event = json.loads(archive.read_text(encoding="utf-8").splitlines()[1])
    assert event == {
        "outcome": "human_release",
        "event": "mutation_human_release",
        "released_at": NOW.isoformat(),
    }


def test_libera_registro_legado_sem_pasta_completed(tmp_path: Path) -> None:
    (tmp_path / (KEY + ".jsonl")).write_text(
        '{"intent":"mutation","previous_state":"unknown"}\n', encoding="utf-8"
    )
    journal = FileMutationJournal(tmp_path)
    assert release_mutation(journal, KEY, interactive=True, confirm=lambda _: True, now=lambda: NOW)
    assert journal.list_pending() == ()
    assert len(list((tmp_path / "completed").iterdir())) == 1


@pytest.mark.parametrize("key", ["../outside", "", "a" * 63])
def test_recusa_identificador_invalido(tmp_path: Path, key: str) -> None:
    with pytest.raises(ConfigError):
        release_mutation(
            FileMutationJournal(tmp_path),
            key,
            interactive=True,
            confirm=lambda _: True,
            now=lambda: NOW,
        )


def test_cancelamento_preserva_pendencia(tmp_path: Path) -> None:
    journal = FileMutationJournal(tmp_path)
    journal.begin(KEY, "unknown")
    assert not release_mutation(
        journal, KEY, interactive=True, confirm=lambda _: False, now=lambda: NOW
    )
    assert len(journal.list_pending()) == 1
