"""Caso de uso `spec inspect`: resumo e verificações cruzadas para o agente."""

from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.openapi import load_spec
from harness_dast.application.inspect_report import SpecInspection
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.profile import ProductProfile
from tests.fakes.probe_ports import InMemoryDocuments
from tests.fakes.rig import STR, Rig, agenda_flows, agenda_profile, operation, profile_data
from tests.unit.api_helpers import rule, rules_from


def inspect(rig: Rig, budget: int = 40_000) -> SpecInspection:
    return rig.inspect().execute("agenda", budget)


def test_summary_describes_the_operations_of_the_openapi() -> None:
    result = inspect(Rig())

    assert result.summary.operation_count == 8
    assert {op.id for op in result.summary.operations} >= {"criar", "buscar"}


def test_operations_that_will_never_be_sent_are_listed_with_their_reason() -> None:
    result = inspect(Rig(flows=agenda_flows()))

    reasons = {n.operation_id: n.reason for n in result.not_sent}
    assert reasons == {
        "admin": "skipped_denied",
        "externo": "skipped_scope",
        "remover": "skipped_destructive",
    }
    assert all(n.message for n in result.not_sent)


def test_openapi_servers_outside_the_scope_are_reported() -> None:
    spec = ApiSpec(
        title="T",
        version="1",
        servers=(
            "https://api.hml.acme-teste.net.br",
            "https://producao.acme.com.br/v1",
            "/relativo",
        ),
        operations=(operation("ler", "get", "/api/ler"),),
    )

    result = inspect(Rig(spec=spec))

    assert len(result.servers_out_of_scope) == 1
    assert "producao.acme.com.br" in result.servers_out_of_scope[0]


def test_rules_that_match_no_field_are_reported_by_position() -> None:
    rules = rules_from(rule("nome", "alphanumeric"), rule("campo_inexistente", "alphanumeric"))

    result = inspect(Rig(rules=rules))

    assert [(r.number, r.field) for r in result.unused_rules] == [(2, "campo_inexistente")]
    assert result.data_rules.present is True
    assert result.data_rules.valid is True
    assert result.data_rules.count == 2


def test_rule_for_an_unknown_operation_becomes_an_issue_not_an_error() -> None:
    rules = rules_from(rule("nome", "alphanumeric", operation="fantasma"))

    result = inspect(Rig(rules=rules))

    assert [i.code for i in result.issues] == ["DATA_RULES_MISMATCH"]
    assert result.data_rules.valid is False


def test_flows_with_unknown_field_become_an_issue() -> None:
    flows = FlowSpec.from_data(
        {
            "schema_version": 1,
            "bindings": [
                {
                    "produces": {"operation": "criar", "field": "naoexiste"},
                    "consumed_by": [{"operation": "buscar", "param": "pacienteId"}],
                }
            ],
        }
    )

    result = inspect(Rig(flows=flows))

    assert [i.code for i in result.issues] == ["FLOWS_MISMATCH"]
    assert result.flows.valid is False


def test_structurally_invalid_documents_are_reported_as_issues() -> None:
    documents = InMemoryDocuments(
        rules_error=ConfigError("data-rules.yml inválido", hint="corrija"),
        flows_error=ConfigError("flows.yml inválido"),
    )

    result = inspect(Rig(documents=documents))

    assert [i.code for i in result.issues] == ["DATA_RULES_INVALID", "FLOWS_INVALID"]
    assert result.data_rules.present is True
    assert result.data_rules.valid is False
    assert result.flows.valid is False


def test_missing_documents_are_not_issues() -> None:
    result = inspect(Rig())

    assert result.issues == ()
    assert result.data_rules.present is False
    assert result.flows.present is False


def test_required_field_with_an_ungeneratable_pattern_needs_a_rule_until_one_is_written() -> None:
    hard = Schema(type="string", pattern="^(?=a)b$")
    spec = ApiSpec(
        title="T",
        version="1",
        operations=(
            operation("ok", "get", "/api/ok"),
            operation(
                "dificil", "post", "/api/dificil", body={"codigo": hard}, required=("codigo",)
            ),
        ),
    )

    before = inspect(Rig(spec=spec))
    after = inspect(Rig(spec=spec, rules=rules_from(rule("codigo", "numeric", digits=4))))

    assert [n.operation_id for n in before.needs_rule] == ["dificil"]
    assert before.needs_rule[0].hint is not None
    assert after.needs_rule == ()


def test_flow_consumers_are_not_simulated_without_their_producer_values() -> None:
    result = inspect(Rig(flows=agenda_flows()))

    assert result.needs_rule_unchecked == ("atualizar", "buscar", "remover")


def test_destructive_looking_operations_are_flagged_for_deny_paths() -> None:
    spec = ApiSpec(
        title="T",
        version="1",
        operations=(
            operation("popular", "get", "/api/createdb"),
            operation("ler", "get", "/api/ler"),
        ),
    )

    assert inspect(Rig(spec=spec)).suspicious_operations == ("popular",)


def test_budget_limits_the_size_of_the_summary() -> None:
    spec = ApiSpec(
        title="T",
        version="1",
        operations=tuple(
            operation(f"op{i}", "post", f"/api/r{i}", body={"nome": STR}, required=("nome",))
            for i in range(120)
        ),
    )

    result = inspect(Rig(spec=spec), budget=2_000)

    assert len(result.summary.model_dump_json()) <= 2_000
    assert result.summary.omitted_operations > 0


def test_unknown_product_is_a_config_error() -> None:
    with pytest.raises(ConfigError):
        Rig().inspect().execute("nao-existe")


def test_only_data_rules_with_no_problems_count_as_valid() -> None:
    result = inspect(Rig(rules=DataRules(schema_version=1, rules=())))

    assert result.data_rules.present is True
    assert result.data_rules.valid is True
    assert result.data_rules.count == 0


def test_profile_with_deny_path_makes_the_matching_operation_denied() -> None:
    profile = agenda_profile(scope={**profile_data()["scope"], "deny_paths": ["/api/pacientes/**"]})

    result = inspect(Rig(profile=profile))

    denied = {n.operation_id for n in result.not_sent if n.reason == "skipped_denied"}
    assert {"listar", "criar", "buscar"} <= denied


def _two_account_profile(**auth: Any) -> ProductProfile:
    data = profile_data()
    data["auth"]["accounts"].append(
        {
            "alias": "user_b",
            "role": "outro",
            "username": {"secret_ref": "env:ACME_USER_B_LOGIN"},
            "password": {"secret_ref": "env:ACME_USER_B_SENHA"},
        }
    )
    data["auth"].update(auth)
    return ProductProfile.from_data(data)


def test_it_reports_which_account_each_sent_operation_will_use() -> None:
    profile = _two_account_profile(account_map=[{"account": "user_b", "operations": ["criar"]}])

    result = inspect(Rig(profile=profile))

    accounts = {item.operation_id: item.account for item in result.operation_accounts}
    assert accounts["criar"] == "user_b"
    assert accounts["listar"] == "user_a"
    assert "admin" not in accounts


def test_an_account_map_with_an_unknown_operation_becomes_an_issue() -> None:
    profile = _two_account_profile(account_map=[{"account": "user_b", "operations": ["nada"]}])

    result = inspect(Rig(profile=profile))

    assert [issue.code for issue in result.issues] == ["ACCOUNT_MAP_MISMATCH"]


def test_invalid_declared_example_is_reported_without_its_value() -> None:
    schema = Schema(type="string", min_length=10, declared_examples=("secreto",))
    spec = ApiSpec(
        title="T",
        version="1",
        operations=(operation("criar", "post", "/api/x", body={"nome": schema}),),
    )

    result = inspect(Rig(spec=spec))

    assert [issue.code for issue in result.issues] == ["EXAMPLE_LENGTH"]
    assert "secreto" not in result.model_dump_json()


def test_local_openapi_examples_reach_inspection(tmp_path: Path) -> None:
    document = tmp_path / "spec.yml"
    document.write_text(
        """openapi: 3.1.0
info: {title: Teste, version: '1'}
paths:
  /api/x:
    post:
      operationId: criar
      parameters:
        - name: codigo
          in: query
          schema: {type: integer}
          example: segredo
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required: [id]
              properties:
                nome: {type: string, minLength: 5}
            examples:
              invalido:
                value: {nome: xyz}
      responses:
        '200': {description: ok}
""",
        encoding="utf8",
    )

    result = inspect(Rig(spec=load_spec(document)))

    assert [issue.code for issue in result.issues] == [
        "EXAMPLE_TYPE",
        "EXAMPLE_REQUIRED",
        "EXAMPLE_LENGTH",
    ]
    assert "segredo" not in result.model_dump_json()
    assert "xyz" not in result.model_dump_json()


def test_invalid_example_reference_does_not_block_spec_loading(tmp_path: Path) -> None:
    document = tmp_path / "spec.yml"
    document.write_text(
        """openapi: 3.0.0
info: {title: Teste, version: '1'}
paths:
  /api/x:
    get:
      parameters:
        - name: id
          in: query
          schema: {type: string}
          examples:
            ausente: {$ref: '#/components/examples/ausente'}
            remoto: {$ref: 'https://invalid.example/exemplo'}
      responses:
        '200': {description: ok}
""",
        encoding="utf8",
    )

    result = inspect(Rig(spec=load_spec(document)))

    assert result.issues == ()
