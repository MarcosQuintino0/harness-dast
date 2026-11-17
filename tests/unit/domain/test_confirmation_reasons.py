"""Regressões para os motivos de recusa da confirmação."""

import pytest

from harness_dast.domain.confirmation import plan_confirmation
from harness_dast.domain.verification import VerificationEntry
from tests.unit.domain.test_confirmation import MARKER, exchange, finding, scan


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_refuses_passive_rule_when_no_recipe_exists(method: str) -> None:
    result = plan_confirmation(
        finding("10010", method), (exchange(method),), (scan(),), MARKER, "https://example.test"
    )

    assert isinstance(result, VerificationEntry)
    assert result.level == "not_verifiable"
    assert result.reason == "Não há receita segura para este tipo de achado."


@pytest.mark.parametrize("method", ["POST", "DELETE"])
@pytest.mark.parametrize("plugin", ["40018", "40022", "40012", "90022"])
def test_refuses_write_when_recipe_exists(plugin: str, method: str) -> None:
    result = plan_confirmation(
        finding(plugin, method), (exchange(method),), (scan(),), MARKER, "https://example.test"
    )

    assert isinstance(result, VerificationEntry)
    assert result.level == "not_verifiable"
    assert (
        result.reason == "Escritas e DELETE não são repetidos sem autorização e diário comprovados."
    )
