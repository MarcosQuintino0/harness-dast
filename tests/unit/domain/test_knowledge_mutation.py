"""Política de identificadores e projeção do diário de mutações."""

import json
from datetime import UTC, datetime

import pytest

from harness_dast.domain.knowledge_mutation import (
    build_mutation_intent,
    safe_mutation_metadata,
    valid_mutation_intent,
    valid_mutation_key,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("value", ["", "../outside", "a" * 63, "A" * 64, "a" * 65])
def test_chave_recusa_formato_inseguro(value: str) -> None:
    assert not valid_mutation_key(value)


def test_chave_aceita_hexadecimal_comprimento_exato() -> None:
    assert valid_mutation_key("a" * 64)


def test_intencao_legada_e_valida() -> None:
    assert valid_mutation_intent('{"intent":"mutation","previous_state":"unknown"}')


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "{",
        "{}",
        '{"intent":"mutation"}',
        '{"intent":"mutation","previous_state":"unknown","extra":true}',
        '{"intent":"mutation","previous_state":"unknown","previous_state":"present"}',
    ],
)
def test_intencao_recusa_entrada_malformada(raw: str) -> None:
    assert not valid_mutation_intent(raw)


def test_intencao_preserva_metadados_na_projecao() -> None:
    metadata = safe_mutation_metadata("createItem", "user_a", "POST", "run-1", NOW)
    assert metadata is not None
    intent = build_mutation_intent("unknown", None, metadata)
    assert valid_mutation_intent(json.dumps(intent))
    assert intent["metadata"] == metadata.model_dump(mode="json")


@pytest.mark.parametrize("operation", ["", "read/item", "read item", "x" * 201])
def test_metadados_inseguros_sao_omitidos_sem_rejeitar_operacao(operation: str) -> None:
    assert safe_mutation_metadata(operation, "user_a", "POST", "run-1", NOW) is None
