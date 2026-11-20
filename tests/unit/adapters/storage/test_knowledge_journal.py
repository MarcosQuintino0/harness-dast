"""Testes do diário de intenções e resultados desconhecidos."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.mutation_snapshot import MutationSnapshot


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


def test_snapshot_e_gravado_antes_do_resultado_e_sobrevive_a_interrupcao(tmp_path: Path) -> None:
    key = "e" * 64
    journal = FileMutationJournal(tmp_path)
    journal.begin(key, "present", MutationSnapshot(field="price", value=12.5, source="observed"))
    record = json.loads((tmp_path / (key + ".jsonl")).read_text())
    assert record == {
        "intent": "mutation",
        "previous_state": "present",
        "snapshot": {"field": "price", "value": 12.5, "source": "observed"},
    }
    with pytest.raises(ConfigError):
        FileMutationJournal(tmp_path).begin(key, "unknown")
    journal.finish(key, "observed")
    assert len(list((tmp_path / "completed").iterdir())) == 1


def test_snapshot_adulterado_nao_e_persistido_ou_exposto_em_erro(tmp_path: Path) -> None:
    key = "f" * 64
    unsafe = MutationSnapshot.model_construct(field="password", value=123, source="observed")
    with pytest.raises(ConfigError) as error:
        FileMutationJournal(tmp_path).begin(key, "present", unsafe)
    assert "123" not in str(error.value)
    assert not (tmp_path / (key + ".jsonl")).exists()


def test_linha_de_base_nao_e_tratada_como_estado_observado(tmp_path: Path) -> None:
    key = "a" * 64
    snapshot = MutationSnapshot(field="price", value=1, source="request_baseline")
    with pytest.raises(ConfigError):
        FileMutationJournal(tmp_path).begin(key, "present", snapshot)
    FileMutationJournal(tmp_path).begin(key, "unknown", snapshot)


def test_pendencia_existente_explica_resultado_desconhecido_e_como_reconciliar(
    tmp_path: Path,
) -> None:
    key = "c" * 64
    FileMutationJournal(tmp_path).begin(key, "unknown")

    with pytest.raises(ConfigError) as caught:
        FileMutationJournal(tmp_path).begin(key, "unknown")

    assert "Já existe mutação com resultado desconhecido" in caught.value.message
    assert f"hdast mutation release {key}" in (caught.value.hint or "")
    assert "pessoa" in (caught.value.hint or "")


def test_falha_de_io_no_diario_nao_se_passa_por_pendencia(tmp_path: Path) -> None:
    blocker = tmp_path / "ocupado"
    blocker.write_text("arquivo no lugar da pasta", encoding="utf-8")

    with pytest.raises(ConfigError) as caught:
        FileMutationJournal(blocker).begin("d" * 64, "unknown")

    assert "resultado desconhecido" not in caught.value.message
    assert "gravar" in caught.value.message
