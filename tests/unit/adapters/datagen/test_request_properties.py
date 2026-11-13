"""Propriedades: toda requisição gerada satisfaz o esquema (oráculo independente)."""

from typing import Literal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.request_builder import RequestBuilder
from tests.unit.api_helpers import NOW, TAG, body_operation, builder, obj, rule, rules_from
from tests.unit.schema_oracle import conforms

PATTERNS = ["^[A-Z]{3}[0-9]{2}$", r"^\d{4}$", "^[a-z]+$", "[0-9]{3}", r"^\w{2,5}$"]
STRING_FORMATS = [None, None, "uuid", "email", "date", "date-time", "uri"]


@st.composite
def string_schemas(draw: st.DrawFn) -> Schema:
    fmt = draw(st.sampled_from(STRING_FORMATS))
    pattern = draw(st.sampled_from([None, None, *PATTERNS])) if fmt is None else None
    low = draw(st.integers(min_value=0, max_value=6))
    high = draw(st.one_of(st.none(), st.integers(min_value=max(low, 6), max_value=40)))
    enum = draw(st.sampled_from([None, None, None, ("alfa", "beta")]))
    if enum is not None:
        return Schema(type="string", enum=enum)
    return Schema(type="string", format=fmt, pattern=pattern, min_length=low, max_length=high)


@st.composite
def number_schemas(draw: st.DrawFn) -> Schema:
    kind: Literal["integer", "number"] = draw(st.sampled_from(["integer", "number"]))
    low = draw(st.one_of(st.none(), st.integers(min_value=-50, max_value=50)))
    span = draw(st.integers(min_value=3, max_value=500))
    high = None if low is None and draw(st.booleans()) else (low or 0) + span
    return Schema(
        type=kind,
        format=draw(st.sampled_from([None, "int32", "int64"])) if kind == "integer" else None,
        minimum=low,
        maximum=high,
        exclusive_minimum=low is not None and draw(st.booleans()),
        exclusive_maximum=draw(st.booleans()) and high is not None,
    )


def schemas(depth: int) -> st.SearchStrategy[Schema]:
    leaves = st.one_of(string_schemas(), number_schemas(), st.just(Schema(type="boolean")))
    if depth == 0:
        return leaves
    inner = st.deferred(lambda: schemas(depth - 1))
    objects = st.dictionaries(
        st.sampled_from(["a", "b", "c", "d"]), inner, min_size=1, max_size=3
    ).flatmap(
        lambda props: st.sets(st.sampled_from(sorted(props))).map(
            lambda req: obj(tuple(sorted(req)), **props)
        )
    )
    arrays = st.tuples(inner, st.integers(0, 3), st.integers(3, 6)).map(
        lambda t: Schema(type="array", items=t[0], min_items=t[1], max_items=t[2])
    )
    merged = st.tuples(inner, inner).map(lambda t: Schema(all_of=t))
    return st.one_of(leaves, objects, arrays, merged)


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(schemas(2), st.integers(min_value=0, max_value=10_000))
def test_every_generated_body_satisfies_the_schema_it_was_built_from(
    schema: Schema, seed: int
) -> None:
    try:
        built = builder(seed=seed).build(body_operation(schema))
    except ConfigError:
        return  # o harness recusou pedindo uma regra: nunca devolve valor inválido

    assert conforms(schema, built.body)


@settings(max_examples=100, deadline=None)
@given(schemas(2), st.integers(min_value=0, max_value=10_000))
def test_the_same_seed_always_builds_the_same_request(schema: Schema, seed: int) -> None:
    operation = body_operation(schema)

    def attempt() -> object:
        try:
            return builder(seed=seed).build(operation)
        except ConfigError as error:
            return error.message

    assert attempt() == attempt()


def test_unique_rules_never_repeat_across_thousands_of_requests() -> None:
    rules = rules_from(
        rule("cpf", "br.cpf", unique=True),
        rule("codigo", "numeric", unique=True, digits=8),
        rule("email", "email", unique=True),
        rule("nome", "alphanumeric", unique=True, prefix="qa"),
    )
    operation = body_operation(
        obj(
            ("cpf", "codigo", "email", "nome"),
            cpf=Schema(type="string"),
            codigo=Schema(type="string"),
            email=Schema(type="string", format="email"),
            nome=Schema(type="string"),
        )
    )
    montador = RequestBuilder(rules, GeneratorCatalogue(3, NOW), TAG)
    seen: dict[str, set[str]] = {key: set() for key in ("cpf", "codigo", "email", "nome")}

    for _ in range(2500):
        body = montador.build(operation).body
        assert isinstance(body, dict)
        for key, bucket in seen.items():
            bucket.add(str(body[key]))

    assert all(len(bucket) == 2500 for bucket in seen.values())


def test_unique_values_carry_the_run_tag_so_cleanup_can_find_them() -> None:
    rules = rules_from(
        rule("email", "email", unique=True), rule("nome", "alphanumeric", unique=True)
    )
    operation = body_operation(
        obj(("email", "nome"), email=Schema(type="string"), nome=Schema(type="string"))
    )

    body = builder(rules).build(operation).body

    assert isinstance(body, dict)
    assert TAG in str(body["email"])
    assert TAG in str(body["nome"])
