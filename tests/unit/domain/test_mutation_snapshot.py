"""Contrato conservador de snapshot anterior à mutação."""

import pytest

from harness_dast.domain.mutation_snapshot import project_snapshot


@pytest.mark.parametrize("source", ["observed", "request_baseline"])
def test_snapshot_preserva_apenas_escalar_e_origem(source: str) -> None:
    from typing import Literal, cast

    # Parametrização fornece exatamente os dois literais declarados acima.
    origin = cast(Literal["observed", "request_baseline"], source)
    snapshot = project_snapshot("price", 12.5, origin)
    assert snapshot is not None
    assert snapshot.model_dump() == {"field": "price", "value": 12.5, "source": source}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("owner_id", 12),
        ("password", 4),
        ("email", 5),
        ("price", "secret"),
        ("price", {"id": 1}),
        ("price", 1e50),
        ("price", 10**1000),
        ("opaque", 42),
    ],
)
def test_snapshot_recusa_ids_segredos_estruturas_e_valores_sem_significado(
    field: str, value: object
) -> None:
    from typing import cast

    from harness_dast.domain.api_schema import JsonValue

    # Os casos parametrizados são valores JSON de entrada externa.
    assert project_snapshot(field, cast(JsonValue, value), "observed") is None


def test_snapshot_recusa_campo_de_credencial_declarado_no_perfil() -> None:
    assert project_snapshot("price", 12, "observed", forbidden=frozenset({"PRICE"})) is None
