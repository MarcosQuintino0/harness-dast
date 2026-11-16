"""Recibos emitidos só por operações 2xx e sem valores de requisição."""

from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.probe_ports import reply
from tests.fakes.rig import Rig, agenda_flows, default_handler
from tests.unit.api_helpers import rule, rules_from


def test_registra_regra_e_encadeamento_efetivamente_usados() -> None:
    rules = rules_from(rule("nome", "alphanumeric", operation="criar"))
    rig = Rig(flows=agenda_flows(), rules=rules)
    result = rig.probe().execute(ProbeRequest(product="agenda", only=("buscar",)))
    creating, reading = result.operations
    assert creating.outcome == "success"
    assert len(creating.rule_uses) == 1
    receipt = creating.rule_uses[0]
    assert (receipt.operation, receipt.rule_index, receipt.field, receipt.generator) == (
        "criar",
        0,
        "nome",
        "alphanumeric",
    )
    assert [
        (r.producer, r.consumer, r.source_field, r.target_field) for r in reading.flow_uses
    ] == [("criar", "buscar", "id", "pacienteId")]
    sent = next(request for request in rig.target.requests if request.operation_id == "criar")
    assert sent.body is not None
    assert sent.body.decode() not in receipt.model_dump_json()


def test_falha_nao_registra_receita_como_observada() -> None:
    def reject(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id == "criar":
            return reply(400, {})
        response = default_handler(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig = Rig(rules=rules_from(rule("nome", "alphanumeric", operation="criar")), handler=reject)
    result = rig.probe().execute(ProbeRequest(product="agenda", only=("criar",)))
    assert result.operations[0].outcome != "success"
    assert result.operations[0].rule_uses == ()
    assert result.operations[0].flow_uses == ()
