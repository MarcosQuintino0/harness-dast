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


def test_recibo_de_campo_em_array_confere_contra_schema() -> None:
    from harness_dast.domain.api_model import ApiSpec
    from harness_dast.domain.api_schema import Schema
    from harness_dast.domain.knowledge_checks import ensure_rule_use
    from harness_dast.domain.knowledge_receipts import KnowledgeRuleUse
    from tests.unit.api_helpers import body_operation, obj

    schema = obj(
        ("items",), items=Schema(type="array", items=obj(("nome",), nome=Schema(type="string")))
    )
    operation = body_operation(schema, operation_id="criar")
    spec = ApiSpec(title="T", version="1", operations=(operation,))
    rules = rules_from(rule("items.nome", "alphanumeric", operation="criar"))
    receipt = KnowledgeRuleUse(
        operation="criar",
        rule_index=0,
        generator="alphanumeric",
        field="items.nome",
        location="body",
    )
    ensure_rule_use(receipt, rules, spec)


def test_fluxo_nao_emite_recibo_quando_destino_readonly_foi_ignorado() -> None:
    from harness_dast.domain.api_schema import Schema
    from harness_dast.domain.flow import FlowSpec
    from tests.fakes.rig import agenda_spec, operation

    original = agenda_spec()
    consumer = operation(
        "consumer", "post", "/api/other", body={"field": Schema(type="integer", read_only=True)}
    )
    spec = original.model_copy(update={"operations": (*original.operations, consumer)})
    flows = FlowSpec.from_data(
        {
            "schema_version": 1,
            "bindings": [
                {
                    "produces": {"operation": "criar", "field": "id"},
                    "consumed_by": [{"operation": "consumer", "field": "field"}],
                }
            ],
        }
    )
    rig = Rig(spec=spec, flows=flows)
    result = rig.probe().execute(ProbeRequest(product="agenda", only=("consumer",)))
    assert result.operations[-1].outcome == "success"
    assert result.operations[-1].flow_uses == ()
