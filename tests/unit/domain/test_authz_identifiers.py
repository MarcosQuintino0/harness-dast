"""Identificador de objeto no caminho e na consulta (ADR 0042)."""

import pytest

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.authz_findings import identifier_severity
from harness_dast.domain.authz_identifiers import (
    IdentifierRef,
    find_identifiers,
    is_identifier_name,
    query_pairs,
)
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.rig import INT, STR, operation, parameter

UUID = "123e4567-e89b-12d3-a456-426614174000"


def query_op(*params: tuple[str, Schema]) -> Operation:
    return operation(
        "lista",
        "get",
        "/api/consultas",
        parameters=tuple(parameter(name, schema, "query") for name, schema in params),
    )


def exchange(
    target: str, path: str = "/api/consultas", account: str = "pac_a", method: str = "GET"
) -> ExchangeRecord:
    return ExchangeRecord(
        operation_id="lista", method=method, path=path, target=target, account=account, status=200
    )


def found(target: str, *params: tuple[str, Schema], extra: tuple[str, ...] = ()) -> list[str]:
    scan = find_identifiers(query_op(*params), exchange(target), (), extra)
    return [f"{ref.where}:{ref.name}" for ref in scan.refs]


@pytest.mark.parametrize("name", ["pacienteId", "paciente_id", "userUuid", "id", "ownerGuid"])
def test_names_ending_in_an_identifier_word_are_identifiers(name: str) -> None:
    assert is_identifier_name(name)


@pytest.mark.parametrize(
    "name", ["requestId", "traceId", "correlationId", "sessionId", "page", "size", "status", "sort"]
)
def test_volatile_and_ordinary_names_are_not_identifiers(name: str) -> None:
    assert not is_identifier_name(name)


def test_declared_names_are_identifiers_even_without_the_id_suffix() -> None:
    assert is_identifier_name("cpf", ("cpf",))
    assert not is_identifier_name("cpf")


def test_a_query_parameter_with_an_integer_value_is_an_identifier() -> None:
    assert found("/api/consultas?pacienteId=2", ("pacienteId", INT)) == ["query:pacienteId"]


def test_uuid_and_short_text_values_are_identifiers() -> None:
    assert found(f"/api/consultas?userUuid={UUID}", ("userUuid", STR)) == ["query:userUuid"]
    assert found("/api/consultas?contaId=abc-123_Z", ("contaId", STR)) == ["query:contaId"]


def test_a_parameter_the_openapi_does_not_declare_is_never_tested() -> None:
    assert found("/api/consultas?pacienteId=2") == []
    assert found("/api/consultas?pacienteId=2", ("outroId", INT)) == []


def test_a_header_parameter_with_the_same_name_does_not_count() -> None:
    op = operation(
        "lista", "get", "/api/consultas", parameters=(parameter("pacienteId", INT, "header"),)
    )

    scan = find_identifiers(op, exchange("/api/consultas?pacienteId=2"))

    assert scan.refs == ()


def test_ordinary_filters_and_volatile_ids_are_not_identifiers() -> None:
    target = "/api/consultas?page=1&size=10&status=ativo&requestId=99&sessionId=12345678"
    params = tuple((n, INT) for n in ("page", "size", "status", "requestId", "sessionId"))

    assert found(target, *params) == []


def test_an_enum_or_a_long_or_array_schema_is_not_an_identifier() -> None:
    enum = Schema(type="string", enum=("a", "b"))
    long = Schema(type="string", max_length=500)
    array = Schema(type="array", items=INT)

    assert found("/api/consultas?tipoId=a", ("tipoId", enum)) == []
    assert found("/api/consultas?tipoId=abcdef", ("tipoId", long)) == []
    assert found("/api/consultas?tipoId=1", ("tipoId", array)) == []


@pytest.mark.parametrize("value", ["", "1,2,3", "../x", "%zz", "a%20b", "12;13", "ab"])
def test_values_without_the_shape_of_an_identifier_are_ambiguous_and_not_tested(value: str) -> None:
    scan = find_identifiers(
        query_op(("pacienteId", STR)), exchange(f"/api/consultas?pacienteId={value}")
    )

    assert scan.refs == ()
    assert scan.ambiguous == ("pacienteId",)


def test_a_repeated_query_parameter_is_ambiguous() -> None:
    op = query_op(("pacienteId", INT))

    scan = find_identifiers(op, exchange("/api/consultas?pacienteId=1&pacienteId=2"))

    assert scan.refs == ()
    assert scan.ambiguous == ("pacienteId",)


def test_an_integer_with_more_than_18_digits_is_ambiguous() -> None:
    scan = find_identifiers(
        query_op(("pacienteId", INT)), exchange(f"/api/consultas?pacienteId={'1' * 19}")
    )

    assert scan.refs == ()
    assert scan.ambiguous == ("pacienteId",)


def test_an_integer_schema_needs_digits() -> None:
    scan = find_identifiers(
        query_op(("pacienteId", INT)), exchange("/api/consultas?pacienteId=abcdef")
    )

    assert scan.refs == ()
    assert scan.ambiguous == ("pacienteId",)


@pytest.mark.parametrize(
    "target",
    [
        "/api/consultas?",
        "/api/consultas?&&",
        "/api/consultas?=",
        "/api/consultas?%zz",
        "/api/consultas?a=b=c&",
    ],
)
def test_a_malformed_query_never_raises(target: str) -> None:
    scan = find_identifiers(query_op(("pacienteId", INT)), exchange(target))

    assert scan.refs == ()


def test_query_pairs_skips_empty_names_and_keeps_raw_values() -> None:
    assert query_pairs("/x?a=1&&=2&b&c=%20") == [("a", "1"), ("b", ""), ("c", "%20")]


def test_path_markers_are_identifiers_with_no_confidence() -> None:
    item = exchange("/api/pacientes/2/consultas/3", "/api/pacientes/{pid}/consultas/{id}")

    scan = find_identifiers(None, item)

    assert scan.refs == (IdentifierRef("path", "pid"), IdentifierRef("path", "id"))


def test_the_value_is_an_owned_hint_when_it_is_a_path_identifier_of_the_same_account() -> None:
    patient = exchange("/api/pacientes/2", "/api/pacientes/{id}")

    scan = find_identifiers(
        query_op(("pacienteId", INT)), exchange("/api/consultas?pacienteId=2"), (patient,)
    )

    assert scan.refs == (IdentifierRef("query", "pacienteId", "owned_hint"),)


def test_the_value_is_name_only_when_the_path_identifier_is_from_another_account() -> None:
    other = exchange("/api/pacientes/2", "/api/pacientes/{id}", account="pac_b")

    scan = find_identifiers(
        query_op(("pacienteId", INT)), exchange("/api/consultas?pacienteId=2"), (other,)
    )

    assert scan.refs == (IdentifierRef("query", "pacienteId", "name_only"),)


def test_declared_id_parameters_add_candidates() -> None:
    assert found("/api/consultas?cpf=12345678901", ("cpf", STR), extra=("cpf",)) == ["query:cpf"]


def test_path_and_query_identifiers_come_together_path_first() -> None:
    op = operation(
        "lista",
        "get",
        "/api/pacientes/{id}/consultas",
        parameters=(parameter("id"), parameter("medicoId", INT, "query")),
    )
    item = exchange("/api/pacientes/2/consultas?medicoId=3", "/api/pacientes/{id}/consultas")

    scan = find_identifiers(op, item)

    assert [(r.where, r.name) for r in scan.refs] == [("path", "id"), ("query", "medicoId")]
    assert scan.query_refs == (IdentifierRef("query", "medicoId", "name_only"),)


def test_severity_is_high_for_path_and_owned_hint_and_medium_for_name_only() -> None:
    name_only = (IdentifierRef("query", "categoriaId", "name_only"),)
    owned = (IdentifierRef("query", "pacienteId", "owned_hint"),)

    assert identifier_severity("/api/x/{id}", ()) == "high"
    assert identifier_severity("/api/x/{id}", name_only) == "high"
    assert identifier_severity("/api/x", owned) == "high"
    assert identifier_severity("/api/x", name_only) == "medium"
