import json
from pathlib import Path

import pytest

from harness_dast.adapters.openapi import load_spec
from harness_dast.adapters.openapi.refs import MAX_DOCUMENT_NODES, MAX_FILE_BYTES
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import flatten_schema
from harness_dast.domain.errors import ConfigError

FIXTURES = Path(__file__).parents[3] / "fixtures" / "specs"


def load_fixture(name: str) -> ApiSpec:
    return load_spec(FIXTURES / name)


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def query_schema(schema: str) -> str:
    return (
        "openapi: 3.0.0\npaths: {/a: {get: {parameters: [{name: q, in: query, schema: "
        + schema
        + "}]}}}"
    )


def fail(path: Path) -> ConfigError:
    with pytest.raises(ConfigError) as caught:
        load_spec(path)
    return caught.value


def test_load_spec_reads_the_real_vampi_document() -> None:
    spec = load_fixture("vampi.yml")

    assert (spec.title, spec.version) == ("VAmPI", "0.1")
    assert len(spec.operations) == 14
    assert spec.servers == ("http://localhost:5000",)
    assert spec.security_schemes == {"bearerAuth": "http-bearer"}


def test_load_spec_maps_vampi_parameters_bodies_security_and_responses() -> None:
    spec = load_fixture("vampi.yml")
    update = spec.get_operation("api_views.users.update_email")

    assert update.method == "put"
    assert update.path == "/users/v1/{username}/email"
    assert update.parameters[0].location == "path"
    assert update.parameters[0].required
    assert update.request_body is not None
    assert update.request_body.required
    assert update.requires_auth
    assert update.success_codes == ("204",)
    assert not spec.get_operation("api_views.main.basic").requires_auth
    assert spec.get_operation("api_views.users.login_user").tags == ("users",)


def test_load_spec_is_deterministic() -> None:
    assert load_fixture("vampi.yml") == load_fixture("vampi.yml")


def test_load_spec_synthesizes_missing_operation_ids_and_resolves_collisions() -> None:
    spec = load_fixture("no_operation_ids.yaml")

    ids = [op.operation_id for op in spec.operations]
    assert ids == ["get_a_by_id", "get_a_by_id_2", "get_root", "post_pessoas_by_pessoaId_enderecos"]
    assert all(op.id_synthesized for op in spec.operations)


def test_load_spec_survives_recursive_schemas_by_truncating_the_cycle() -> None:
    spec = load_fixture("recursive.yaml")

    body = spec.get_operation("criarNo").request_body
    assert body is not None
    schema = body.media[0].body_schema
    assert schema is not None
    assert schema.properties["parent"].truncated
    children = schema.properties["children"].items
    assert children is not None
    assert children.truncated
    assert not schema.properties["name"].truncated


@pytest.mark.parametrize(
    ("name", "kind"),
    [("remote_ref.yaml", "remota"), ("external_ref.yaml", "arquivo externo")],
)
def test_load_spec_rejects_remote_and_external_refs_without_echoing_them(
    name: str, kind: str
) -> None:
    error = fail(FIXTURES / name)

    assert kind in error.message
    assert "#/paths/~1x/post/requestBody" in error.message
    assert "schemas.example.test" not in error.message
    assert "outro.yaml" not in error.message


def test_load_spec_rejects_swagger_2_with_a_conversion_hint() -> None:
    error = fail(FIXTURES / "swagger2.yaml")

    assert "Swagger 2.0" in error.message
    assert "fora do escopo da V1" in (error.hint or "")


def test_load_spec_rejects_invalid_yaml_with_the_line_and_no_content() -> None:
    error = fail(FIXTURES / "invalid.yaml")

    assert "YAML válido" in error.message
    assert "linha" in error.message


def test_load_spec_rejects_duplicate_operation_ids_naming_the_second_location() -> None:
    error = fail(FIXTURES / "duplicate_ids.yaml")

    assert "'mesmo'" in error.message
    assert "#/paths/~1b/get" in error.message


def test_load_spec_flattens_all_of_composition_and_resolves_parameter_refs() -> None:
    spec = load_fixture("allof.yaml")
    create = spec.get_operation("criarPaciente")

    body = create.request_body
    assert body is not None
    assert body.media[0].body_schema is not None
    flat = flatten_schema(body.media[0].body_schema)
    assert set(flat.required) == {"nome", "cpf"}
    response = create.success_schema()
    assert response is not None
    assert "id" in flatten_schema(response).properties
    fetch = spec.get_operation("buscarPaciente")
    assert fetch.parameters[0].name == "pacienteId"
    assert fetch.parameters[0].required


def test_load_spec_applies_global_security_and_lets_an_operation_clear_it() -> None:
    spec = load_fixture("allof.yaml")

    assert spec.get_operation("criarPaciente").requires_auth
    assert not spec.get_operation("buscarPaciente").requires_auth


def test_load_spec_normalizes_openapi_31_type_arrays_const_and_exclusive_bounds() -> None:
    spec = load_fixture("oas31.yaml")
    body = spec.get_operation("criarItem").request_body
    assert body is not None
    assert body.media[0].body_schema is not None
    props = body.media[0].body_schema.properties

    assert (props["codigo"].type, props["codigo"].nullable) == ("string", True)
    assert props["quantidade"].minimum == 0
    assert props["quantidade"].exclusive_minimum
    assert props["tipo"].enum == ("A",)
    assert props["data"].example == "2020-01-01"
    assert spec.version == "1.0"


def test_load_spec_normalizes_openapi_30_boolean_exclusive_bounds_and_nullable(
    tmp_path: Path,
) -> None:
    text = """
openapi: 3.0.0
info: {title: t, version: "1"}
paths:
  /a:
    post:
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                n:
                  type: integer
                  minimum: 1
                  exclusiveMinimum: true
                  nullable: true
                  enum: [1, 2, null]
      responses: {"200": {description: ok}}
"""
    spec = load_spec(write(tmp_path, "a.yaml", text))
    body = spec.operations[0].request_body
    assert body is not None
    assert body.media[0].body_schema is not None
    n = body.media[0].body_schema.properties["n"]

    assert n.exclusive_minimum
    assert n.nullable
    assert n.enum == (1, 2)


def test_load_spec_accepts_json_documents(tmp_path: Path) -> None:
    document = {
        "openapi": "3.0.0",
        "info": {"title": "J", "version": "2"},
        "paths": {"/a": {"get": {"responses": {"200": {"description": "ok"}}}}},
    }

    spec = load_spec(write(tmp_path, "a.json", json.dumps(document)))

    assert spec.title == "J"
    assert spec.operations[0].operation_id == "get_a"


def test_load_spec_reports_invalid_json_with_the_line(tmp_path: Path) -> None:
    error = fail(write(tmp_path, "a.json", '{\n "openapi": \n'))

    assert "JSON válido" in error.message
    assert "linha 3" in error.message


def test_load_spec_accepts_a_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.yaml"
    path.write_bytes(b"\xef\xbb\xbfopenapi: 3.0.0\ninfo: {title: B, version: '1'}\npaths: {}\n")

    assert load_spec(path).title == "B"


def test_load_spec_rejects_a_file_over_the_size_limit(tmp_path: Path) -> None:
    path = tmp_path / "big.yaml"
    path.write_bytes(b"#" * (MAX_FILE_BYTES + 1))

    assert "MiB" in fail(path).message


def test_load_spec_rejects_a_missing_file_without_a_traceback(tmp_path: Path) -> None:
    error = fail(tmp_path / "nada.yaml")

    assert "Não foi possível ler" in error.message
    assert "'nada.yaml'" in error.message


def test_load_spec_rejects_a_non_utf8_file(tmp_path: Path) -> None:
    path = tmp_path / "latin.yaml"
    path.write_bytes(b"openapi: 3.0.0\n# \xe9\xe9\n")

    assert "UTF-8" in fail(path).message


def test_load_spec_rejects_a_yaml_alias_bomb(tmp_path: Path) -> None:
    levels = ["a: &a0 [x, x, x, x, x, x, x, x, x, x]"]
    levels += [f"b{i}: &a{i} [" + ", ".join([f"*a{i - 1}"] * 10) + "]" for i in range(1, 9)]
    text = "openapi: 3.0.0\ninfo: {title: t, version: '1'}\npaths: {}\n" + "\n".join(levels)

    error = fail(write(tmp_path, "bomb.yaml", text))

    assert str(MAX_DOCUMENT_NODES) in error.message


def test_load_spec_rejects_a_self_referencing_yaml_structure(tmp_path: Path) -> None:
    text = "openapi: 3.0.0\ninfo: {title: t, version: '1'}\npaths: {}\nloop: &l [*l]\n"

    assert "aninhamento" in fail(write(tmp_path, "loop.yaml", text)).message


def test_load_spec_rejects_deeply_nested_documents(tmp_path: Path) -> None:
    nested = "[" * 200 + "]" * 200
    text = f"openapi: 3.0.0\ninfo: {{title: t, version: '1'}}\npaths: {{}}\nx: {nested}\n"

    assert "aninhamento" in fail(write(tmp_path, "deep.yaml", text)).message


def test_load_spec_rejects_absurdly_deep_nesting_without_recursion_errors(tmp_path: Path) -> None:
    text = "x: " + "[" * 100_000

    error = fail(write(tmp_path, "abyss.yaml", text))

    assert isinstance(error, ConfigError)


def test_load_spec_rejects_absurdly_deep_json(tmp_path: Path) -> None:
    error = fail(write(tmp_path, "abyss.json", "[" * 200_000))

    assert isinstance(error, ConfigError)


def test_load_spec_truncates_schemas_nested_beyond_the_depth_limit(tmp_path: Path) -> None:
    schema: dict[str, object] = {"type": "string"}
    for _ in range(30):
        schema = {"type": "object", "properties": {"n": schema}}
    document = {
        "openapi": "3.0.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/a": {"post": {"requestBody": {"content": {"application/json": {"schema": schema}}}}}
        },
    }

    spec = load_spec(write(tmp_path, "deep.json", json.dumps(document)))

    cursor = spec.operations[0].request_body.media[0].body_schema  # type: ignore[union-attr]  # montado acima
    depth = 0
    while cursor is not None and not cursor.truncated:
        cursor = cursor.properties.get("n")
        depth += 1
    assert 20 < depth < 30


def test_load_spec_rejects_exponential_ref_expansion(tmp_path: Path) -> None:
    schemas: dict[str, object] = {"S0": {"type": "string"}}
    for i in range(1, 25):
        schemas[f"S{i}"] = {
            "type": "object",
            "properties": {k: {"$ref": f"#/components/schemas/S{i - 1}"} for k in "ab"},
        }
    document = {
        "openapi": "3.0.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/a": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/S24"}}
                        }
                    }
                }
            }
        },
        "components": {"schemas": schemas},
    }

    assert "esquemas" in fail(write(tmp_path, "boom.json", json.dumps(document))).message


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("[1, 2]", "objeto na raiz"),
        ("just text", "objeto na raiz"),
        ("info: {}", "não declara a versão"),
        ("openapi: 4.0.0", "não suportada"),
        ("openapi: 3.0.0\npaths: []", "#/paths"),
        ("openapi: 3.0.0\npaths: {a: {}}", "começar com '/'"),
        ("openapi: 3.0.0\npaths: {/a: 5}", "#/paths/~1a"),
        ("openapi: 3.0.0\npaths: {/a: {get: {parameters: {}}}}", "parameters"),
        ("openapi: 3.0.0\npaths: {/a: {get: {parameters: [{in: query}]}}}", "name"),
        ("openapi: 3.0.0\npaths: {/a: {get: {parameters: [{name: q, in: body}]}}}", "/in"),
        ("openapi: 3.0.0\npaths: {/a: {get: {operationId: 5}}}", "operationId"),
        ("openapi: 3.0.0\npaths: {/a: {get: {security: x}}}", "security"),
        ("openapi: 3.0.0\npaths: {/a: {get: {security: [x]}}}", "security"),
        ("openapi: 3.0.0\npaths: {/a: {get: {responses: x}}}", "responses"),
        ("openapi: 3.0.0\npaths: {/a: {get: {requestBody: {content: x}}}}", "content"),
        (query_schema("5"), "esquema"),
        (query_schema("{type: foo}"), "/type"),
        (query_schema("{minLength: -1}"), "minLength"),
        (query_schema("{minLength: x}"), "minLength"),
        (query_schema("{properties: 3}"), "properties"),
        (query_schema("{allOf: 3}"), "allOf"),
        (query_schema("{enum: 3}"), "enum"),
        (query_schema("{required: 3}"), "required"),
        (query_schema("{format: 3}"), "format"),
        (query_schema("{minimum: x}"), "minimum"),
        (query_schema("{$ref: 3}"), "$ref"),
        (query_schema("{$ref: '#/nada'}"), "inexistente"),
    ],
)
def test_load_spec_reports_malformed_documents_with_a_location_and_no_traceback(
    tmp_path: Path, text: str, fragment: str
) -> None:
    error = fail(write(tmp_path, "bad.yaml", text))

    assert fragment in error.message
    assert len(error.message) < 400


def test_load_spec_rejects_a_ref_chain_that_never_ends(tmp_path: Path) -> None:
    text = """
openapi: 3.0.0
info: {title: t, version: '1'}
paths:
  /a:
    post:
      requestBody: {$ref: '#/components/requestBodies/A'}
components:
  requestBodies:
    A: {$ref: '#/components/requestBodies/B'}
    B: {$ref: '#/components/requestBodies/A'}
"""
    assert "longa demais" in fail(write(tmp_path, "loop.yaml", text)).message


def test_load_spec_follows_percent_encoded_and_escaped_pointers_and_list_indexes(
    tmp_path: Path,
) -> None:
    text = """
openapi: 3.0.0
info: {title: t, version: '1'}
paths:
  /a:
    post:
      requestBody:
        content:
          application/json:
            schema: {$ref: '#/components/schemas/Odd%20Name~1x~0y'}
  /b:
    post:
      requestBody:
        content:
          application/json:
            schema: {$ref: '#/x-list/0'}
x-list:
  - {type: integer}
components:
  schemas:
    "Odd Name/x~y": {type: string}
"""
    spec = load_spec(write(tmp_path, "ptr.yaml", text))

    first = spec.operations[0].request_body
    second = spec.operations[1].request_body
    assert first is not None
    assert first.media[0].body_schema is not None
    assert first.media[0].body_schema.type == "string"
    assert second is not None
    assert second.media[0].body_schema is not None
    assert second.media[0].body_schema.type == "integer"


def test_load_spec_handles_yaml_numeric_keys_boolean_schemas_and_dates(tmp_path: Path) -> None:
    text = """
openapi: 3.1.0
info: {title: 3, version: 1.5}
servers: [{url: 'https://api.test'}, 5]
paths:
  /a:
    parameters:
      - {name: h, in: header, schema: true}
    post:
      parameters:
        - name: h
          in: header
          required: true
          content:
            application/json: {schema: {type: integer}}
        - {name: ok, in: query, schema: {type: string, enum: [2020-01-01, 3, 1.5, [x], .inf]}}
      responses:
        200:
          description: ok
          content:
            application/json:
              schema: {type: object, properties: {id: {type: string}}}
        default: {description: erro}
x-extra: 1
"""
    spec = load_spec(write(tmp_path, "y.yaml", text))
    op = spec.operations[0]

    assert (spec.title, spec.version, spec.servers) == ("3", "1.5", ("https://api.test",))
    assert [(p.name, p.required) for p in op.parameters] == [("h", True), ("ok", False)]
    assert op.parameters[0].value_schema.type == "integer"
    assert op.parameters[1].value_schema.enum == ("2020-01-01", 3, 1.5)
    assert op.success_codes == ("200",)


def test_load_spec_ignores_x_extensions_among_the_paths_but_rejects_other_names(
    tmp_path: Path,
) -> None:
    text = "openapi: 3.0.0\ninfo: {title: t, version: '1'}\npaths: {x-meta: {a: 1}}\n"

    assert load_spec(write(tmp_path, "x.yaml", text)).operations == ()


def test_load_spec_reports_a_domain_validation_failure_with_the_operation_location(
    tmp_path: Path,
) -> None:
    text = (
        "openapi: 3.0.0\ninfo: {title: t, version: '1'}\n"
        'paths: {/a: {get: {operationId: "a\\nb"}}}\n'
    )

    error = fail(write(tmp_path, "ctl.yaml", text))

    assert "#/paths/~1a/get" in error.message
    assert "operation_id" in error.message


def test_load_spec_never_echoes_long_hostile_text(tmp_path: Path) -> None:
    hostile = "A" * 5000
    text = f"openapi: 3.0.0\npaths: {{/a: {{get: {{operationId: '{hostile}'}}}}}}\n"

    error = fail(write(tmp_path, "h.yaml", text))

    assert hostile not in error.message
    assert len(error.message) < 300
