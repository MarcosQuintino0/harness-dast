"""Testes offline do conhecimento e da invalidação seletiva."""

from datetime import UTC, datetime

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge import Knowledge
from harness_dast.domain.strategy_basis import StrategyBasisContext


def _data() -> dict[str, object]:
    basis = dict.fromkeys(
        (
            "environment",
            "authorization",
            "accounts",
            "planning",
            "openapi",
            "data_rules",
            "flows",
            "engine",
        ),
        "a" * 64,
    )
    return {
        "schema_version": 1,
        "basis": basis,
        "references": {
            "target": "target.yml",
            "data_rules": "data-rules.yml",
            "flows": "flows.yml",
        },
        "entries": [
            {
                "kind": "flow",
                "source": "contract",
                "reason": "references_existing_documents",
                "state": "validated",
                "valid_until": "2027-01-01",
                "dependencies": [
                    "environment",
                    "authorization",
                    "openapi",
                    "flows",
                    "engine",
                    "planning",
                ],
            },
            {
                "kind": "account",
                "source": "owner",
                "reason": "references_existing_documents",
                "state": "validated",
                "valid_until": "2027-01-01",
                "dependencies": ["environment", "authorization", "accounts", "engine", "planning"],
            },
            {
                "kind": "data",
                "source": "contract",
                "reason": "references_existing_documents",
                "state": "validated",
                "valid_until": "2027-01-01",
                "dependencies": [
                    "environment",
                    "authorization",
                    "openapi",
                    "data_rules",
                    "engine",
                    "planning",
                ],
            },
            {
                "kind": "effect",
                "source": "observation",
                "reason": "references_existing_documents",
                "state": "validated",
                "valid_until": "2027-01-01",
                "dependencies": [
                    "environment",
                    "authorization",
                    "accounts",
                    "openapi",
                    "flows",
                    "engine",
                    "planning",
                ],
            },
            {
                "kind": "authentication",
                "source": "owner",
                "reason": "references_existing_documents",
                "state": "validated",
                "valid_until": "2027-01-01",
                "dependencies": ["environment", "authorization", "accounts", "engine", "planning"],
            },
        ],
    }


def test_review_invalida_apenas_dependencias_alteradas() -> None:
    knowledge = Knowledge.from_data(_data())
    current = knowledge.basis.model_dump()
    current["flows"] = "b" * 64
    assert knowledge.review(
        StrategyBasisContext.model_validate(current), datetime(2026, 1, 1, tzinfo=UTC)
    ) == (("flows",), (), (), ("flows",), ())


@pytest.mark.parametrize(
    "data", [{}, {"schema_version": True}, None, {"schema_version": 1, "basis": {}, "entries": []}]
)
def test_entrada_invalida_recusada(data: object) -> None:
    with pytest.raises(ConfigError):
        Knowledge.from_data(data)


def test_dependencias_incompletas_recusadas() -> None:
    data = _data()
    data["entries"] = [
        {
            "kind": "flow",
            "source": "observation",
            "reason": "references_existing_documents",
            "state": "validated",
            "valid_until": "2027-01-01",
            "dependencies": ["environment"],
        }
    ]
    with pytest.raises(ConfigError):
        Knowledge.from_data(data)


def test_campos_livres_recusados_sem_eco() -> None:
    data = _data()
    data["token"] = "valor-confidencial"  # noqa: S105 - valor sint?tico de teste
    with pytest.raises(ConfigError) as error:
        Knowledge.from_data(data)
    assert "valor-confidencial" not in str(error.value)
