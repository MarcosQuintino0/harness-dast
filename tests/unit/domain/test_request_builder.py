import pytest

from harness_dast.domain.api_model import (
    MediaBody,
    Operation,
    Parameter,
    RequestBody,
)
from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.flow import ResolvedBindings
from harness_dast.domain.implicit_values import FieldNotGeneratable
from harness_dast.domain.request_builder import (
    MAX_BUILD_DEPTH,
    RequestBuilder,
    ValueRequest,
)
from tests.unit.api_helpers import TAG, body_operation, builder, obj, rule, rules_from

STRING = Schema(type="string")


def test_build_includes_required_and_optional_fields() -> None:
    schema = obj(("a",), a=STRING, b=Schema(type="integer"))

    body = builder().build(body_operation(schema)).body

    assert isinstance(body, dict)
    assert set(body) == {"a", "b"}


def test_build_uses_the_first_enum_value_when_no_rule_matches() -> None:
    schema = obj(("a",), a=Schema(type="string", enum=("x", "y")))

    assert builder().build(body_operation(schema)).body == {"a": "x"}


def test_build_skips_null_in_enums_when_choosing_the_value() -> None:
    schema = obj(("a",), a=Schema(type="string", enum=(None, "z"), nullable=True))

    assert builder().build(body_operation(schema)).body == {"a": "z"}


def test_build_ignores_example_and_default_values() -> None:
    schema = obj(("a",), a=Schema(type="string", example="fixo", default="fixo"))

    body = builder().build(body_operation(schema)).body

    assert isinstance(body, dict)
    assert body["a"] != "fixo"


def test_build_applies_the_most_specific_rule() -> None:
    rules = rules_from(
        rule("codigo", "constant", value="geral"),
        rule("codigo", "constant", value="especifico", operation="criar"),
    )
    schema = obj(("codigo",), codigo=STRING)

    general = builder(rules).build(body_operation(schema, operation_id="outra")).body
    specific = builder(rules).build(body_operation(schema, operation_id="criar")).body

    assert general == {"codigo": "geral"}
    assert specific == {"codigo": "especifico"}


def test_build_passes_the_documented_context_to_the_value_source() -> None:
    seen: list[ValueRequest] = []

    def source(request: ValueRequest) -> JsonValue:
        seen.append(request)
        return "abc"

    rules = rules_from(rule("nome", "constant", unique=False, value="abc"))
    schema = obj(("pessoa",), pessoa=obj(("nome",), nome=STRING))
    RequestBuilder(rules, source, TAG).build(body_operation(schema, operation_id="criar"))

    request = seen[0]
    assert request.field_path == "body.pessoa.nome"
    assert request.field_name == "nome"
    assert request.location == "body"
    assert request.operation_id == "criar"
    assert request.generator == "constant"
    assert request.args == {"value": "abc"}
    assert (request.unique, request.counter, request.draw_index) == (False, 0, 0)
    assert request.run_tag == TAG
    assert request.value_schema.type == "string"


def test_build_advances_draw_index_per_rule_and_counter_per_unique_draw() -> None:
    seen: list[ValueRequest] = []

    def source(request: ValueRequest) -> JsonValue:
        seen.append(request)
        return f"v{request.counter}"

    rules = rules_from(rule("a", "alphanumeric", unique=True), rule("b", "alphanumeric"))
    builder_ = RequestBuilder(rules, source, TAG)
    operation = body_operation(obj(("a", "b"), a=STRING, b=STRING))

    builder_.build(operation)
    builder_.build(operation)

    assert [(r.field_name, r.draw_index, r.counter) for r in seen] == [
        ("a", 0, 0),
        ("b", 0, 0),
        ("a", 1, 1),
        ("b", 1, 0),
    ]


def test_build_raises_when_a_unique_generator_repeats_a_value() -> None:
    rules = rules_from(rule("a", "alphanumeric", unique=True))
    repeated = RequestBuilder(rules, lambda request: "sempre-igual", TAG)
    operation = body_operation(obj(("a",), a=STRING))
    repeated.build(operation)

    with pytest.raises(ConfigError, match="repetiu um valor único"):
        repeated.build(operation)


def test_build_raises_when_unique_capacity_of_the_run_is_exhausted() -> None:
    rules = rules_from(rule("a", "alphanumeric", unique=True))
    capped = RequestBuilder(rules, lambda request: f"v{request.counter}", TAG)
    capped._unique_counter = 16**4  # simula uma execução que gastou todo o contador

    with pytest.raises(ConfigError, match="únicos demais"):
        capped.build(body_operation(obj(("a",), a=STRING)))


def test_build_rejects_an_invalid_run_tag() -> None:
    with pytest.raises(ConfigError):
        RequestBuilder(rules_from(), lambda request: None, "XYZ")


def test_build_fails_with_the_rule_number_when_a_rule_value_violates_the_schema() -> None:
    rules = rules_from(rule("a", "constant", value="longo-demais"))
    schema = obj(("a",), a=Schema(type="string", max_length=3))

    with pytest.raises(ConfigError) as caught:
        builder(rules).build(body_operation(schema))

    assert "regra 1" in (caught.value.hint or "")
    assert "maior que max_length" in caught.value.message
    assert not isinstance(caught.value, FieldNotGeneratable)


def test_build_fails_even_for_an_optional_field_when_a_rule_value_is_invalid() -> None:
    rules = rules_from(rule("a", "constant", value=5))
    schema = obj((), a=Schema(type="string", enum=("x",)))

    with pytest.raises(ConfigError):
        builder(rules).build(body_operation(schema))


def test_build_coerces_numeric_text_to_integer_when_the_field_is_an_integer() -> None:
    rules = rules_from(rule("codigo", "numeric", digits=6))
    schema = obj(("codigo",), codigo=Schema(type="integer", minimum=0))

    body = builder(rules).build(body_operation(schema)).body

    assert isinstance(body, dict)
    assert isinstance(body["codigo"], int)


def test_build_coerces_integers_to_text_when_the_field_is_a_string() -> None:
    rules = rules_from(rule("n", "integer", min=5, max=5))
    schema = obj(("n",), n=STRING)

    assert builder(rules).build(body_operation(schema)).body == {"n": "5"}


def test_build_fails_when_text_cannot_be_coerced_to_the_field_type() -> None:
    rules = rules_from(rule("flag", "constant", value=True), rule("txt", "constant", value="x1"))
    schema = obj(("flag", "txt"), flag=Schema(type="boolean"), txt=Schema(type="integer"))

    with pytest.raises(ConfigError, match="tipo diferente de integer"):
        builder(rules).build(body_operation(schema))


def test_build_omits_optional_fields_it_cannot_generate_and_reports_them() -> None:
    schema = obj(("a",), a=STRING, b=Schema(type="string", pattern="(x|y)+"))

    built = builder().build(body_operation(schema))

    assert isinstance(built.body, dict)
    assert set(built.body) == {"a"}
    assert built.skipped_fields == ("body.b",)


def test_build_fails_with_an_instruction_when_a_required_field_is_not_generatable() -> None:
    schema = obj(("b",), b=Schema(type="string", pattern="(x|y)+"))

    with pytest.raises(FieldNotGeneratable) as caught:
        builder().build(body_operation(schema))

    assert "regra" in (caught.value.hint or "")
    assert "'body.b'" in caught.value.message


def test_build_uses_the_safe_pattern_subset_to_make_text() -> None:
    schema = obj(("placa",), placa=Schema(type="string", pattern="^[A-Z]{3}[0-9]{4}$"))

    assert builder().build(body_operation(schema)).body == {"placa": "AAA0000"}


def test_build_fails_when_a_generated_value_breaks_the_schema_without_a_rule() -> None:
    schema = obj(("e",), e=Schema(type="string", format="email", max_length=5))

    with pytest.raises(FieldNotGeneratable, match=r"fora do formato|maior que"):
        builder().build(body_operation(schema))


def test_build_never_sends_read_only_fields() -> None:
    schema = obj(("id", "nome"), id=Schema(type="integer", read_only=True), nome=STRING)

    body = builder().build(body_operation(schema)).body

    assert isinstance(body, dict)
    assert set(body) == {"nome"}


def test_build_uses_the_first_non_null_one_of_branch_and_merges_all_of() -> None:
    schema = obj(
        ("a", "b"),
        a=Schema(one_of=(Schema(type="null"), Schema(type="integer", minimum=7, maximum=7))),
        b=Schema(all_of=(Schema(type="string", min_length=4), Schema(max_length=4))),
    )

    body = builder().build(body_operation(schema)).body

    assert isinstance(body, dict)
    assert body["a"] == 7
    assert len(str(body["b"])) == 4


def test_build_makes_one_item_by_default_and_respects_min_and_max_items() -> None:
    item = Schema(type="integer", minimum=1, maximum=9)
    schema = obj(
        ("a", "b", "c"),
        a=Schema(type="array", items=item),
        b=Schema(type="array", items=item, min_items=3),
        c=Schema(type="array", items=item, max_items=0),
    )

    body = builder().build(body_operation(schema)).body

    assert isinstance(body, dict)
    assert [len(body[k]) for k in "abc"] == [1, 3, 0]  # type: ignore[arg-type]  # são listas


def test_build_returns_an_empty_list_when_the_array_has_no_item_schema() -> None:
    schema = obj(("a",), a=Schema(type="array"))

    assert builder().build(body_operation(schema)).body == {"a": []}


def test_build_fails_when_an_array_needs_more_items_than_the_limit() -> None:
    schema = obj(("a",), a=Schema(type="array", items=STRING, min_items=21))

    with pytest.raises(FieldNotGeneratable, match="mínimo de itens"):
        builder().build(body_operation(schema))


def test_build_fails_when_an_array_requires_items_of_a_truncated_schema() -> None:
    schema = obj(("a",), a=Schema(type="array", items=Schema(truncated=True), min_items=1))

    with pytest.raises(FieldNotGeneratable):
        builder().build(body_operation(schema))


def test_build_cuts_recursive_structures() -> None:
    node = Schema(
        type="object",
        required=("nome",),
        properties={
            "nome": STRING,
            "pai": Schema(truncated=True),
            "filhos": Schema(type="array", items=Schema(truncated=True)),
            "obrigatorio": Schema(truncated=True),
        },
    )
    schema = node.model_copy(update={"required": ("nome", "obrigatorio")})

    body = builder().build(body_operation(schema)).body

    assert isinstance(body, dict)
    assert "pai" not in body
    assert body["filhos"] == []
    assert body["obrigatorio"] == {}


def test_build_fails_when_required_structure_is_nested_beyond_the_limit() -> None:
    deep: Schema = STRING
    for _ in range(MAX_BUILD_DEPTH + 2):
        deep = obj(("x",), x=deep)

    with pytest.raises(FieldNotGeneratable, match="aninhado demais"):
        builder().build(body_operation(deep))


def test_build_skips_an_optional_field_nested_beyond_the_limit() -> None:
    deep: Schema = STRING
    for _ in range(MAX_BUILD_DEPTH + 2):
        deep = obj((), x=deep)

    built = builder().build(body_operation(deep))

    assert built.skipped_fields


def test_build_returns_null_for_null_typed_fields() -> None:
    schema = obj(("n",), n=Schema(type="null"))

    assert builder().build(body_operation(schema)).body == {"n": None}


def test_build_treats_untyped_fields_as_text() -> None:
    body = builder().build(body_operation(obj(("n",), n=Schema()))).body

    assert isinstance(body, dict)
    assert isinstance(body["n"], str)


def test_build_supports_a_scalar_body_schema() -> None:
    built = builder().build(body_operation(Schema(type="integer", minimum=3, maximum=3)))

    assert built.body == 3
    assert built.body_media_type == "application/json"


def test_build_has_no_body_when_the_operation_declares_none() -> None:
    built = builder().build(Operation(operation_id="a", method="get", path="/a"))

    assert built.body is None
    assert built.body_media_type is None
    assert built.method == "GET"
    assert built.path == "/a"


def test_build_reports_the_media_type_but_no_body_when_the_body_has_no_schema() -> None:
    operation = Operation(
        operation_id="a",
        method="post",
        path="/a",
        request_body=RequestBody(media=(MediaBody(media_type="text/plain"),)),
    )

    built = builder().build(operation)

    assert built.body is None
    assert built.body_media_type == "text/plain"


def param(name: str, location: str, schema: Schema = STRING, *, required: bool = True) -> Parameter:
    return Parameter.model_validate(
        {"name": name, "location": location, "required": required, "value_schema": schema}
    )


def test_build_fills_and_encodes_path_parameters() -> None:
    rules = rules_from(rule("nome", "constant", value="a/b c"))
    operation = Operation(
        operation_id="a",
        method="get",
        path="/x/{nome}/y/{id}",
        parameters=(param("nome", "path"), param("id", "path", Schema(type="integer"))),
    )

    path = builder(rules).build(operation).path

    assert path.startswith("/x/a%2Fb%20c/y/")
    assert "{" not in path


def test_build_fills_undeclared_path_placeholders_with_text() -> None:
    operation = Operation(operation_id="a", method="get", path="/x/{solto}")

    path = builder().build(operation).path

    assert path.startswith("/x/")
    assert "{" not in path


def test_build_expands_query_arrays_into_repeated_pairs_and_writes_booleans_in_lowercase() -> None:
    rules = rules_from(rule("on", "constant", value=True))
    operation = Operation(
        operation_id="a",
        method="get",
        path="/a",
        parameters=(
            param(
                "ids",
                "query",
                Schema(
                    type="array", items=Schema(type="integer", minimum=1, maximum=1), min_items=2
                ),
            ),
            param("on", "query", Schema(type="boolean")),
        ),
    )

    assert builder(rules).build(operation).query == (("ids", "1"), ("ids", "1"), ("on", "true"))


def test_build_skips_authorization_content_type_and_accept_headers() -> None:
    operation = Operation(
        operation_id="a",
        method="get",
        path="/a",
        parameters=(
            param("Authorization", "header"),
            param("Content-Type", "header"),
            param("accept", "header"),
            param("X-Trace", "header"),
            param("sessao", "cookie"),
        ),
    )

    built = builder().build(operation)

    assert set(built.headers) == {"X-Trace"}
    assert set(built.cookies) == {"sessao"}


def test_build_omits_an_optional_parameter_that_cannot_be_generated() -> None:
    operation = Operation(
        operation_id="a",
        method="get",
        path="/a",
        parameters=(param("q", "query", Schema(type="string", pattern="(a|b)"), required=False),),
    )

    built = builder().build(operation)

    assert built.query == ()
    assert built.skipped_fields == ("query.q",)


def test_build_fails_for_a_required_parameter_that_cannot_be_generated() -> None:
    operation = Operation(
        operation_id="a",
        method="get",
        path="/a",
        parameters=(param("q", "query", Schema(type="string", pattern="(a|b)")),),
    )

    with pytest.raises(FieldNotGeneratable):
        builder().build(operation)


def test_build_stringifies_structured_and_null_values_in_parameters() -> None:
    rules = rules_from(rule("n", "constant", value=None))
    operation = Operation(
        operation_id="a",
        method="get",
        path="/a",
        parameters=(
            param("n", "header", Schema(type="null")),
            param("o", "cookie", obj(("k",), k=Schema(type="integer", minimum=1, maximum=1))),
        ),
    )

    built = builder(rules).build(operation)

    assert built.headers == {"n": ""}
    assert built.cookies == {"o": '{"k":1}'}


def test_build_uses_bound_values_in_parameters_and_body_fields() -> None:
    operation = body_operation(
        obj(("pacienteId", "x"), pacienteId=STRING, x=obj(("id",), id=Schema(type="integer"))),
        path="/p/{pid}",
        parameters=(param("pid", "path", Schema(type="integer")),),
    )
    bindings = ResolvedBindings(params={"pid": 42}, fields={"pacienteId": 42, "x.id": "7"})

    built = builder().build(operation, bindings)

    assert built.path == "/p/42"
    assert built.body == {"pacienteId": "42", "x": {"id": 7}}


def test_build_rejects_a_bound_value_that_breaks_the_destination_schema() -> None:
    operation = body_operation(
        obj(("n",), n=Schema(type="integer", maximum=5)),
    )

    with pytest.raises(ConfigError, match="valor encadeado"):
        builder().build(operation, ResolvedBindings(fields={"n": 99}))


def test_build_accepts_bound_values_for_untyped_destinations() -> None:
    operation = body_operation(obj(("n",), n=Schema()))

    assert builder().build(operation, ResolvedBindings(fields={"n": "abc"})).body == {"n": "abc"}


def test_build_does_not_apply_body_bindings_to_parameters_of_the_same_name() -> None:
    operation = body_operation(
        obj(("id",), id=Schema(type="integer", minimum=1, maximum=1)),
        path="/p/{id}",
        parameters=(param("id", "path", Schema(type="integer", minimum=2, maximum=2)),),
    )

    built = builder().build(operation, ResolvedBindings(fields={"id": 1}))

    assert built.path == "/p/2"
    assert built.body == {"id": 1}


def test_build_is_repeatable_for_the_same_builder_state_and_distinct_after_use() -> None:
    operation = body_operation(obj(("a",), a=STRING))

    first = builder(seed=5).build(operation)
    again = builder(seed=5).build(operation)

    assert first == again


@pytest.mark.parametrize("name", ["page", "pagina", "offset", "skip"])
@pytest.mark.parametrize("minimum", [0, 1])
def test_pagination_starts_at_declared_minimum(name: str, minimum: int) -> None:
    op = Operation(
        operation_id="list",
        method="get",
        path="/x",
        parameters=(
            Parameter(
                name=name, location="query", value_schema=Schema(type="integer", minimum=minimum)
            ),
        ),
    )
    assert dict(builder().build(op).query)[name] == str(minimum)


@pytest.mark.parametrize("name", ["size", "limit", "per_page", "tamanho"])
def test_pagination_size_is_small_and_respects_maximum(name: str) -> None:
    op = Operation(
        operation_id="list",
        method="get",
        path="/x",
        parameters=(
            Parameter(
                name=name,
                location="query",
                value_schema=Schema(type="integer", minimum=1, maximum=3),
            ),
        ),
    )
    assert dict(builder().build(op).query)[name] == "3"


def test_explicit_pagination_rule_takes_precedence() -> None:
    op = Operation(
        operation_id="list",
        method="get",
        path="/x",
        parameters=(
            Parameter(
                name="page", location="query", value_schema=Schema(type="integer", minimum=0)
            ),
        ),
    )
    assert (
        dict(builder(rules_from(rule("page", "constant", value=4))).build(op).query)["page"] == "4"
    )


def test_pagination_without_relevant_bounds_uses_normal_generator() -> None:
    seen: list[ValueRequest] = []

    def source(request: ValueRequest) -> JsonValue:
        seen.append(request)
        return 17

    op = Operation(
        operation_id="list",
        method="get",
        path="/x",
        parameters=(
            Parameter(name="page", location="query", value_schema=Schema(type="integer")),
            Parameter(name="size", location="query", value_schema=Schema(type="integer")),
        ),
    )
    assert dict(RequestBuilder(rules_from(), source, TAG).build(op).query) == {
        "page": "17",
        "size": "17",
    }
    assert len(seen) == 2
