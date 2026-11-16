"""Prévia simbólica preserva entradas declaradas e não afirma execução."""

from harness_dast.domain.api_model import ApiSpec, Operation, Parameter
from harness_dast.domain.strategy_preview import preview
from tests.fakes.profile_data import valid_profile


def test_previa_descreve_operacao_sem_afirmar_cobertura() -> None:
    profile = valid_profile()
    operation = Operation(
        operation_id="listar",
        method="get",
        path="/items",
        parameters=(Parameter(name="page", location="query"),),
    )
    spec = ApiSpec(title="Exemplo", version="1", operations=(operation,))

    result = preview(profile, spec, None)

    assert result.coverage == "pending_probe_and_zap"
    assert result.operations[0].entries[0].name == "page"
    assert result.operations[0].entries[0].location == "query"
    assert result.operations[0].account == profile.account_for("listar", "GET", "/items")
    assert result.operations[0].body_entries_complete is False
    assert result.model_dump(mode="json")["coverage"] == "pending_probe_and_zap"
