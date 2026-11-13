# ruff: noqa: SIM105, S105
"""QA independente do leitor de OpenAPI (`adapters/openapi/loader.py`).

Contrato (docstring): o documento é entrada NÃO CONFIÁVEL; o leitor não abre URL nem outro
arquivo, limita tamanho, nós, profundidade e expansão de `$ref`, recusa Swagger 2.0 e versões
desconhecidas, e só levanta `ConfigError`.
"""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.openapi.loader import load_spec
from harness_dast.adapters.openapi.refs import MAX_FILE_BYTES
from harness_dast.domain.errors import ConfigError

OK = {"200": {"description": "ok"}}


def doc(**extra: object) -> dict[str, object]:
    return {"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "paths": {}, **extra}


def op(operation_id: str = "op", **extra: object) -> dict[str, object]:
    return {"operationId": operation_id, "responses": OK, **extra}


def write(tmp_path: Path, content: object, name: str = "api.json") -> Path:
    path = tmp_path / name
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return path


def test_load_spec_reads_a_minimal_valid_document(tmp_path: Path) -> None:
    spec = load_spec(write(tmp_path, doc(paths={"/a": {"get": op("a")}})))

    assert [item.operation_id for item in spec.operations] == ["a"]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{",
        "[]",
        "null",
        "42",
        '"texto"',
        "{}",
        {"swagger": "2.0", "info": {}, "paths": {}},
        {"openapi": "2.0"},
        {"openapi": "4.0.0", "info": {}, "paths": {}},
        {"openapi": 3, "info": {}, "paths": {}},
        {"openapi": "", "info": {}, "paths": {}},
        doc(paths=[]),
        doc(paths={"a": {"get": op()}}),
        doc(paths={"/a": {"get": op("x")}, "/b": {"get": op("x")}}),
        doc(paths={"/a": {"get": {"operationId": "a", "responses": "x"}}}),
        doc(paths={"/a": {"get": {"operationId": "a", "parameters": "x", "responses": OK}}}),
        doc(
            paths={
                "/a": {"get": {"operationId": "a", "parameters": [{"$ref": "x"}], "responses": OK}}
            }
        ),
        doc(
            paths={
                "/a": {"get": {"operationId": "a", "parameters": [{"name": "q"}], "responses": OK}}
            }
        ),
    ],
)
def test_load_spec_refuses_invalid_documents_with_config_error(
    tmp_path: Path, content: object
) -> None:
    with pytest.raises(ConfigError):
        load_spec(write(tmp_path, content))


@pytest.mark.parametrize(
    "ref",
    [
        "http://169.254.169.254/latest/meta-data",
        "https://evil.example.org/schema.json#/x",
        "//evil.example.org/x",
        "file:///etc/passwd",
        "other.json#/x",
        "../secret.yaml#/x",
        "/etc/passwd",
        "ftp://x/y",
        "#",
        "#x",
        "",
    ],
)
def test_load_spec_never_follows_a_non_local_reference(tmp_path: Path, ref: str) -> None:
    content = doc(
        paths={"/a": {"get": {"operationId": "a", "parameters": [{"$ref": ref}], "responses": OK}}}
    )

    with pytest.raises(ConfigError):
        load_spec(write(tmp_path, content))


def test_load_spec_refuses_a_reference_loop_between_parameters(tmp_path: Path) -> None:
    content = doc(
        components={
            "parameters": {
                "A": {"$ref": "#/components/parameters/B"},
                "B": {"$ref": "#/components/parameters/A"},
            }
        },
        paths={
            "/a": {
                "get": {
                    "operationId": "a",
                    "parameters": [{"$ref": "#/components/parameters/A"}],
                    "responses": OK,
                }
            }
        },
    )

    with pytest.raises(ConfigError):
        load_spec(write(tmp_path, content))


@pytest.mark.parametrize("kind", ["self", "mutual", "allof", "items", "oneof"])
def test_load_spec_terminates_on_cyclic_schemas(tmp_path: Path, kind: str) -> None:
    ref = {"$ref": "#/components/schemas/Node"}
    schemas = {
        "self": {"Node": {"type": "object", "properties": {"next": ref}}},
        "mutual": {
            "Node": {"type": "object", "properties": {"b": {"$ref": "#/components/schemas/B"}}},
            "B": {"type": "object", "properties": {"n": ref}},
        },
        "allof": {"Node": {"allOf": [ref]}},
        "items": {"Node": {"type": "array", "items": ref}},
        "oneof": {"Node": {"oneOf": [ref, ref]}},
    }[kind]
    content = doc(
        components={"schemas": schemas},
        paths={
            "/n": {"post": op("n", requestBody={"content": {"application/json": {"schema": ref}}})}
        },
    )

    try:
        load_spec(write(tmp_path, content))
    except ConfigError:
        pass


def test_load_spec_refuses_an_alias_bomb_in_yaml_quickly(tmp_path: Path) -> None:
    import time

    lines = ["openapi: 3.0.3", "info: {title: t, version: '1'}", "x-a0: &a0 [l,l,l,l,l,l,l,l,l]"]
    for level in range(1, 12):
        lines.append(f"x-a{level}: &a{level} [{','.join([f'*a{level - 1}'] * 9)}]")
    lines.append("paths: {}")
    path = write(tmp_path, "\n".join(lines), "bomb.yaml")

    started = time.monotonic()
    with pytest.raises(ConfigError):
        load_spec(path)

    assert time.monotonic() - started < 10


def test_load_spec_refuses_a_file_above_the_size_limit_without_reading_all_of_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "big.json"
    path.write_bytes(b" " * (MAX_FILE_BYTES + 1))

    with pytest.raises(ConfigError):
        load_spec(path)


@pytest.mark.parametrize("depth", [200, 3_000, 50_000])
def test_load_spec_refuses_extremely_nested_json(tmp_path: Path, depth: int) -> None:
    text = '{"openapi":"3.0.3","info":{},"paths":{},"x":' + "[" * depth + "]" * depth + "}"

    with pytest.raises(ConfigError):
        load_spec(write(tmp_path, text))


@pytest.mark.parametrize("digits", [5_000, 50_000])
def test_load_spec_refuses_huge_integers_in_yaml_with_config_error(
    tmp_path: Path, digits: int
) -> None:
    text = "openapi: 3.0.3\ninfo: {title: t, version: '1'}\nx: " + "9" * digits + "\npaths: {}\n"

    with pytest.raises(ConfigError):
        load_spec(write(tmp_path, text, "huge.yaml"))


def test_load_spec_refuses_bytes_that_are_not_utf8(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_bytes(b'{"openapi": "3.0.3", "info": {"title": "\xff\xfe"}}')

    with pytest.raises(ConfigError):
        load_spec(path)


def test_load_spec_refuses_a_missing_file_without_echoing_the_directory(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        load_spec(tmp_path / "nao-existe.json")

    assert str(tmp_path) not in caught.value.message


def test_load_spec_error_messages_never_echo_document_content(tmp_path: Path) -> None:
    secret = "SEGREDO-NO-DOCUMENTO-777"
    content = doc(
        paths={
            "/a": {
                "get": {
                    "operationId": "a",
                    "parameters": [{"$ref": f"http://{secret}/x"}],
                    "responses": OK,
                }
            }
        }
    )

    with pytest.raises(ConfigError) as caught:
        load_spec(write(tmp_path, content))

    assert secret not in caught.value.message
    assert secret not in (caught.value.hint or "")


def test_load_spec_does_not_execute_or_resolve_anything_from_yaml_tags(tmp_path: Path) -> None:
    text = (
        "openapi: 3.0.3\ninfo: {title: t, version: '1'}\npaths: {}\n"
        "x: !!python/object/apply:os.system ['echo executado > saida.txt']\n"
    )

    with pytest.raises(ConfigError):
        load_spec(write(tmp_path, text, "tag.yaml"))

    assert not (tmp_path / "saida.txt").exists()
    assert not Path("saida.txt").exists()
