"""`RequestBuilder` e `encode_built_request` com `multipart/form-data` (ADR 0052)."""

import pytest

from harness_dast.domain.api_model import MediaBody, Operation, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.multipart_encoding import summarize_multipart
from harness_dast.domain.request_builder import BuiltRequest
from harness_dast.domain.request_encoding import encode_body, encode_built_request
from tests.unit.api_helpers import body_operation, builder, obj, rule, rules_from

BINARY = Schema(type="string", format="binary")
STRING = Schema(type="string")
BASE = "https://api.hml.acme-teste.net.br/v2"


def multipart_operation(
    schema: Schema | None,
    part_types: dict[str, str] | None = None,
    *,
    json_too: bool = False,
    operation_id: str = "enviar",
) -> Operation:
    media = [
        MediaBody(
            media_type="multipart/form-data",
            body_schema=schema,
            part_content_types=part_types or {},
        )
    ]
    if json_too:
        media.append(MediaBody(media_type="application/json", body_schema=obj(("x",), x=STRING)))
    return Operation(
        operation_id=operation_id,
        method="post",
        path="/docs",
        request_body=RequestBody(required=True, media=tuple(media)),
    )


def encode(built: BuiltRequest):  # type: ignore[no-untyped-def]  # auxiliar de teste
    return encode_built_request(built, base_url=BASE)


def test_a_required_binary_property_becomes_one_default_text_file() -> None:
    built = builder().build(multipart_operation(obj(("arquivo",), arquivo=BINARY)))

    assert built.body_media_type == "multipart/form-data"
    assert [(f.field, f.kind, f.filename) for f in built.files] == [
        ("arquivo", "text", "synthetic.txt")
    ]
    assert built.body == {}


def test_an_optional_binary_property_is_also_sent() -> None:
    built = builder().build(multipart_operation(obj((), arquivo=BINARY)))

    assert [f.field for f in built.files] == ["arquivo"]


def test_a_list_of_binary_items_becomes_a_single_file_with_the_field_name() -> None:
    built = builder().build(
        multipart_operation(obj(("anexos",), anexos=Schema(type="array", items=BINARY)))
    )

    assert [f.field for f in built.files] == ["anexos"]


def test_scalar_properties_follow_the_usual_path_and_go_as_text_parts() -> None:
    schema = obj(
        ("arquivo", "descricao"),
        arquivo=BINARY,
        descricao=Schema(type="string", enum=("fixa",)),
        ordem=Schema(type="integer"),
    )

    built = builder().build(multipart_operation(schema))

    assert isinstance(built.body, dict)
    assert built.body["descricao"] == "fixa"
    assert isinstance(built.body["ordem"], int)


def test_a_data_rule_still_decides_a_text_part_of_the_multipart() -> None:
    rules = rules_from(rule("descricao", "constant", value="da regra"))
    schema = obj(("arquivo", "descricao"), arquivo=BINARY, descricao=STRING)

    built = builder(rules).build(multipart_operation(schema))

    assert built.body == {"descricao": "da regra"}


def test_a_synthetic_file_rule_chooses_kind_and_name() -> None:
    rules = rules_from(rule("arquivo", "synthetic_file", kind="png", name="foto.png"))

    built = builder(rules).build(multipart_operation(obj(("arquivo",), arquivo=BINARY)))

    assert [(f.kind, f.filename) for f in built.files] == [("png", "foto.png")]


def test_a_synthetic_file_rule_without_a_name_uses_the_default_of_the_kind() -> None:
    rules = rules_from(rule("arquivo", "synthetic_file", kind="csv"))

    built = builder(rules).build(multipart_operation(obj(("arquivo",), arquivo=BINARY)))

    assert [(f.kind, f.filename) for f in built.files] == [("csv", "synthetic.csv")]


def test_the_rule_is_the_most_specific_choice_over_the_declared_encoding() -> None:
    rules = rules_from(rule("arquivo", "synthetic_file", kind="json"))
    operation = multipart_operation(obj(("arquivo",), arquivo=BINARY), {"arquivo": "image/png"})

    built = builder(rules).build(operation)

    assert [f.kind for f in built.files] == ["json"]


def test_the_declared_encoding_content_type_chooses_the_kind() -> None:
    operation = multipart_operation(obj(("arquivo",), arquivo=BINARY), {"arquivo": "image/png"})

    built = builder().build(operation)

    assert [(f.kind, f.filename) for f in built.files] == [("png", "synthetic.png")]


def test_an_unsupported_declared_type_falls_back_to_text_and_says_so() -> None:
    operation = multipart_operation(obj(("arquivo",), arquivo=BINARY), {"arquivo": "image/jpeg"})

    built = builder().build(operation)

    assert [f.kind for f in built.files] == ["text"]
    assert any("image/jpeg" in item for item in built.skipped_fields)


def test_a_non_file_rule_on_a_file_field_is_refused_with_a_hint() -> None:
    rules = rules_from(rule("arquivo", "constant", value="x"))

    with pytest.raises(ConfigError) as info:
        builder(rules).build(multipart_operation(obj(("arquivo",), arquivo=BINARY)))

    assert "synthetic_file" in (info.value.hint or "")


def test_json_stays_the_preferred_type_when_the_operation_has_both() -> None:
    operation = multipart_operation(obj(("arquivo",), arquivo=BINARY), json_too=True)

    built = builder().build(operation)

    assert built.body_media_type == "application/json"
    assert built.files == ()


@pytest.mark.parametrize(
    "schema",
    [
        None,
        Schema(type="object"),
        obj(("a",), a=obj(("b",), b=STRING)),
        obj(("a",), a=Schema(type="array", items=STRING)),
        obj(("a",), a=Schema(type="array", items=obj((), b=STRING))),
        obj(("a",), a=Schema(type="integer", format="binary")),
        obj(("a",), a=Schema(type="object", format="binary")),
    ],
)
def test_unsupported_multipart_schemas_are_a_build_error_with_a_useful_message(
    schema: Schema | None,
) -> None:
    with pytest.raises(ConfigError) as info:
        builder().build(multipart_operation(schema))

    assert "multipart_unsupported_schema" in info.value.message
    assert info.value.hint


def test_format_byte_is_text_and_not_a_file() -> None:
    schema = obj(("conteudo",), conteudo=Schema(type="string", format="byte"))

    built = builder().build(multipart_operation(schema))

    assert built.files == ()
    assert isinstance(built.body, dict)
    assert "conteudo" in built.body


def test_more_than_twenty_parts_is_refused() -> None:
    schema = obj(tuple(f"c{i}" for i in range(21)), **{f"c{i}": STRING for i in range(21)})

    with pytest.raises(ConfigError):
        builder().build(multipart_operation(schema))


@pytest.mark.parametrize("name", ["a b", "é", "a..b", "x" * 65])
def test_a_property_name_outside_the_safe_rule_is_refused_without_echoing_it(name: str) -> None:
    with pytest.raises(ConfigError) as info:
        builder().build(multipart_operation(obj((name,), **{name: BINARY})))

    assert "multipart_unsupported_schema" in info.value.message


def test_read_only_properties_are_not_sent() -> None:
    schema = obj(("arquivo",), arquivo=BINARY, id=Schema(type="integer", read_only=True))

    built = builder().build(multipart_operation(schema))

    assert built.body == {}


def test_encode_built_request_produces_a_multipart_with_the_boundary_in_the_content_type() -> None:
    rules = rules_from(rule("arquivo", "synthetic_file", kind="png", name="foto.png"))
    schema = obj(("arquivo", "descricao"), arquivo=BINARY, descricao=STRING)
    built = builder(rules).build(multipart_operation(schema))

    request = encode(built)

    headers = dict(request.headers)
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=harness-")
    assert request.body is not None
    summary = summarize_multipart(headers["Content-Type"], request.body)
    assert summary is not None
    assert [(p.name, p.kind) for p in summary.parts] == [
        ("descricao", "field"),
        ("arquivo", "file"),
    ]


def test_encode_body_alone_still_refuses_multipart_with_a_message_about_what_is_missing() -> None:
    with pytest.raises(ConfigError) as info:
        encode_body({"a": "b"}, "multipart/form-data")

    assert "arquivos" in info.value.message
    assert "ainda não é testado" not in info.value.message


def test_a_multipart_body_with_nested_values_is_refused_at_encoding() -> None:
    built = BuiltRequest(
        operation_id="x",
        method="POST",
        path="/x",
        body={"a": {"b": 1}},
        body_media_type="multipart/form-data",
    )

    with pytest.raises(ConfigError):
        encode(built)


def test_a_plain_json_operation_is_unchanged_by_the_multipart_branch() -> None:
    built = builder().build(body_operation(obj(("a",), a=STRING)))

    assert built.files == ()
    assert encode(built).body is not None
