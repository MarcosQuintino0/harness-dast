"""Casos independentes de compatibilidade nas dicas de encadeamento."""

from harness_dast.domain.api_model import Operation, Parameter, SuccessResponse
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.spec_hints import suggest_spec_hints
from tests.fakes.rig import agenda_profile
from tests.unit.domain.test_spec_hints import plan


def test_campos_homonimos_com_formatos_incompativeis_nao_sugerem_fluxo() -> None:
    source = Operation(
        operation_id="listar",
        method="get",
        path="/items",
        success_responses=(
            SuccessResponse(
                status="200",
                body_schema=Schema(
                    type="array",
                    items=Schema(
                        type="object", properties={"id": Schema(type="string", format="uuid")}
                    ),
                ),
            ),
        ),
    )
    target = Operation(
        operation_id="buscar",
        method="get",
        path="/items/{id}",
        parameters=(
            Parameter(
                name="id",
                location="path",
                required=True,
                value_schema=Schema(type="string", format="date"),
            ),
        ),
    )
    hints = suggest_spec_hints(agenda_profile(), (source, target), plan(source, target))
    assert not [hint for hint in hints if hint.kind == "flow"]
