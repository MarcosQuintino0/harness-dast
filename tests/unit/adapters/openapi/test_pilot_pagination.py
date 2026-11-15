"""Paginação gerada a partir do contrato real da Clínica Piloto."""

from pathlib import Path

from harness_dast.adapters.openapi import load_spec
from tests.unit.api_helpers import builder


def test_listar_pacientes_uses_first_page_and_small_size() -> None:
    spec = load_spec(Path(__file__).parents[4] / "lab/pilot/openapi.json")
    operation = next(op for op in spec.operations if op.operation_id == "listarPacientes")
    assert dict(builder().build(operation).query) == {"page": "0", "size": "10"}
