import pytest

from harness_dast.domain.api_model import ApiSpec, MediaBody, Operation, Parameter, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import ConfigError
from tests.unit.api_helpers import obj, rule, rules_from


def test_from_data_accepts_the_documented_example() -> None:
    rules = DataRules.from_data(
        {
            "schema_version": 1,
            "rules": [
                {"match": {"field": "cpf"}, "generator": "br.cpf", "unique": True},
                {
                    "match": {"operation": "criarConvenio", "field": "codigo"},
                    "generator": "numeric",
                    "args": {"digits": 8},
                    "unique": True,
                },
                {
                    "match": {"field": "email"},
                    "generator": "email",
                    "args": {"domain": "teste.exemplo.com.br"},
                    "unique": True,
                },
            ],
        }
    )

    assert len(rules.rules) == 3


def test_from_data_accepts_an_empty_rule_list() -> None:
    assert DataRules.from_data({"schema_version": 1}).rules == ()


@pytest.mark.parametrize("data", [None, [], "texto", 3])
def test_from_data_rejects_a_document_that_is_not_a_map(data: object) -> None:
    with pytest.raises(ConfigError, match="deve ser um mapa"):
        DataRules.from_data(data)


def test_from_data_requires_schema_version() -> None:
    with pytest.raises(ConfigError, match="não informa schema_version"):
        DataRules.from_data({"rules": []})


@pytest.mark.parametrize("version", [2, 0, "1", True, 1.0])
def test_from_data_rejects_unsupported_schema_version(version: object) -> None:
    with pytest.raises(ConfigError, match="não é suportada"):
        DataRules.from_data({"schema_version": version})


def test_from_data_rejects_unknown_top_level_field() -> None:
    with pytest.raises(ConfigError, match="campo desconhecido"):
        DataRules.from_data({"schema_version": 1, "regras": []})


def test_from_data_reports_the_path_of_each_invalid_rule() -> None:
    data = {
        "schema_version": 1,
        "rules": [
            {"match": {"field": "a"}, "generator": "br.cpf"},
            {"match": {"field": "b"}, "generator": "nao_existe"},
            {"match": {"field": "c"}, "generator": "numeric"},
            {
                "match": {"field": "d"},
                "generator": "constant",
                "args": {"value": 1},
                "unique": True,
            },
        ],
    }

    with pytest.raises(ConfigError) as caught:
        DataRules.from_data(data)

    message = caught.value.message
    assert message.startswith("Arquivo data-rules.yml inválido (3 problema(s))")
    assert "rules[1]" in message
    assert "rules[2]" in message
    assert "rules[3]" in message
    assert "nao_existe" not in message
    assert "não aceita unique" in message


def test_from_data_rejects_missing_match_field_and_unknown_rule_key() -> None:
    data = {
        "schema_version": 1,
        "rules": [{"match": {}, "generator": "br.cpf", "extra": 1}],
    }

    with pytest.raises(ConfigError) as caught:
        DataRules.from_data(data)

    assert "rules[0].match.field: campo obrigatório ausente" in caught.value.message
    assert "rules[0].extra: campo desconhecido" in caught.value.message


@pytest.mark.parametrize("field", ["", "a b", "a..b", ".a", "a.", "x\ny", "a" * 101])
def test_from_data_rejects_malformed_field_names(field: str) -> None:
    with pytest.raises(ConfigError):
        rules_from(rule(field, "br.cpf"))


@pytest.mark.parametrize("location", ["cabecalho", "BODY", ""])
def test_from_data_rejects_unknown_location(location: str) -> None:
    with pytest.raises(ConfigError):
        rules_from(rule("a", "br.cpf", location=location))


def test_from_data_never_echoes_received_values_in_errors() -> None:
    with pytest.raises(ConfigError) as caught:
        rules_from(rule("a", "numeric", digits="SEGREDO-XYZ"))

    assert "SEGREDO" not in caught.value.message


def test_from_data_rejects_two_rules_with_the_same_match() -> None:
    with pytest.raises(ConfigError, match="mesmo match"):
        rules_from(rule("cpf", "br.cpf"), rule("cpf", "numeric", digits=11))


def test_from_data_allows_rules_that_differ_in_operation_or_location() -> None:
    rules = rules_from(
        rule("cpf", "br.cpf"),
        rule("cpf", "numeric", digits=11, operation="criar"),
        rule("cpf", "numeric", digits=11, location="query"),
    )

    assert len(rules.rules) == 3


def test_from_data_rejects_more_than_500_rules() -> None:
    many = [rule(f"campo{i}", "boolean") for i in range(501)]

    with pytest.raises(ConfigError):
        rules_from(*many)


def test_resolve_returns_none_when_no_rule_matches() -> None:
    assert rules_from(rule("cpf", "br.cpf")).resolve("op", "body", ("nome",)) is None


def test_resolve_matches_by_field_name_in_any_location() -> None:
    rules = rules_from(rule("cpf", "br.cpf"))

    assert rules.resolve("op", "body", ("pessoa", "cpf")) is not None
    assert rules.resolve("op", "query", ("cpf",)) is not None


def test_resolve_prefers_operation_over_a_more_general_rule() -> None:
    rules = rules_from(
        rule("codigo", "numeric", digits=4), rule("codigo", "numeric", digits=8, operation="criar")
    )

    resolved = rules.resolve("criar", "body", ("codigo",))

    assert resolved is not None
    assert resolved.index == 1
    other = rules.resolve("outra", "body", ("codigo",))
    assert other is not None
    assert other.index == 0


def test_resolve_prefers_a_longer_field_path_over_a_shorter_one() -> None:
    rules = rules_from(rule("cpf", "br.cpf"), rule("socio.cpf", "numeric", digits=11))

    resolved = rules.resolve("op", "body", ("empresa", "socio", "cpf"))

    assert resolved is not None
    assert resolved.index == 1
    plain = rules.resolve("op", "body", ("responsavel", "cpf"))
    assert plain is not None
    assert plain.index == 0


def test_resolve_prefers_a_rule_with_location_when_everything_else_is_equal() -> None:
    rules = rules_from(rule("id", "uuid"), rule("id", "numeric", digits=3, location="path"))

    path = rules.resolve("op", "path", ("id",))
    body = rules.resolve("op", "body", ("id",))

    assert path is not None
    assert path.index == 1
    assert body is not None
    assert body.index == 0


def test_resolve_ranks_operation_above_path_depth_above_location() -> None:
    rules = rules_from(
        rule("a.b", "numeric", digits=1, location="body"),
        rule("b", "numeric", digits=2, operation="op"),
    )

    resolved = rules.resolve("op", "body", ("a", "b"))

    assert resolved is not None
    assert resolved.index == 1


def test_resolve_does_not_match_a_path_shorter_than_the_rule() -> None:
    assert rules_from(rule("a.b", "boolean")).resolve("op", "body", ("b",)) is None


def spec_with(*operations: Operation) -> ApiSpec:
    return ApiSpec(title="t", version="1", operations=operations)


def create_operation() -> Operation:
    schema = obj(("nome",), nome=Schema(type="string"), endereco=obj(cep=Schema(type="string")))
    return Operation(
        operation_id="criar",
        method="post",
        path="/x/{id}",
        parameters=(Parameter(name="id", location="path", required=True),),
        request_body=RequestBody(
            media=(MediaBody(media_type="application/json", body_schema=schema),)
        ),
    )


def test_validate_against_returns_the_indexes_of_rules_that_match_nothing() -> None:
    rules = rules_from(
        rule("nome", "boolean"), rule("cpf", "br.cpf"), rule("endereco.cep", "br.cep")
    )

    assert rules.validate_against(spec_with(create_operation())) == (1,)


def test_validate_against_matches_path_parameters() -> None:
    assert rules_from(rule("id", "boolean")).validate_against(spec_with(create_operation())) == ()


def test_validate_against_rejects_an_unknown_operation() -> None:
    rules = rules_from(rule("nome", "boolean", operation="nao\nexiste"))

    with pytest.raises(ConfigError) as caught:
        rules.validate_against(spec_with(create_operation()))

    assert "'nao?existe'" in caught.value.message


def test_validate_against_ignores_operations_without_a_body() -> None:
    operation = Operation(operation_id="a", method="get", path="/a")

    assert rules_from(rule("x", "boolean")).validate_against(spec_with(operation)) == (0,)


def test_validate_against_scans_nested_arrays_and_stops_at_the_depth_limit() -> None:
    deep: Schema = Schema(type="object", properties={"alvo": Schema(type="string")})
    for _ in range(12):
        deep = Schema(type="object", properties={"n": Schema(type="array", items=deep)})
    operation = Operation(
        operation_id="a",
        method="post",
        path="/a",
        request_body=RequestBody(
            media=(MediaBody(media_type="application/json", body_schema=deep),)
        ),
    )

    assert rules_from(rule("n", "boolean")).validate_against(spec_with(operation)) == ()
    assert rules_from(rule("alvo", "boolean")).validate_against(spec_with(operation)) == (0,)


def test_resolve_keeps_the_first_rule_when_a_later_matching_rule_is_less_specific() -> None:
    rules = rules_from(
        rule("codigo", "numeric", digits=8, operation="criar"),
        rule("codigo", "numeric", digits=4),
    )

    resolved = rules.resolve("criar", "body", ("codigo",))

    assert resolved is not None
    assert resolved.index == 0
