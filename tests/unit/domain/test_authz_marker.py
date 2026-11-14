"""Marcador da escrita em recurso de outra conta (ADR 0042)."""

from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.authz_marker import MARKER_SUFFIX, Marker, choose_marker

BODY: dict[str, JsonValue] = {"nome": "Ana", "idade": 30}
BEFORE: JsonValue = {"id": 1, "nome": "Ana", "idade": 30}


def test_text_gets_the_suffix_and_the_current_value_is_kept_to_restore() -> None:
    assert choose_marker(BODY, BEFORE) == Marker("nome", "Ana" + MARKER_SUFFIX, "Ana")


def test_the_marker_is_deterministic() -> None:
    assert choose_marker(BODY, BEFORE) == choose_marker(dict(BODY), dict(BEFORE))  # type: ignore[arg-type]


def test_the_marker_differs_from_the_value_read_not_from_the_value_sent() -> None:
    marker = choose_marker({"nome": "Enviado"}, {"nome": "Atual"})

    assert marker == Marker("nome", "Atual-hdast", "Atual")


def test_the_text_is_truncated_to_fit_max_length() -> None:
    schema = {"nome": Schema(type="string", max_length=10)}

    marker = choose_marker({"nome": "Ana Maria Silva"}, {"nome": "Ana Maria Silva"}, schema)

    assert marker is not None
    assert marker.value == "Ana " + MARKER_SUFFIX
    assert len(str(marker.value)) == 10


def test_a_text_field_without_room_for_the_suffix_is_dropped() -> None:
    schema = {"nome": Schema(type="string", max_length=6)}

    assert choose_marker({"nome": "Ana"}, {"nome": "Ana"}, schema) is None


def test_a_field_whose_marker_would_equal_the_current_value_is_dropped() -> None:
    schema = {"nome": Schema(type="string", max_length=9)}

    assert choose_marker({"nome": "Ana-hdast"}, {"nome": "Ana-hdast"}, schema) is None


def test_integer_goes_up_one_step_when_there_is_no_text() -> None:
    assert choose_marker({"idade": 30}, {"idade": 30}) == Marker("idade", 31, 30)


def test_integer_at_the_maximum_goes_down() -> None:
    schema = {"idade": Schema(type="integer", maximum=30)}

    assert choose_marker({"idade": 30}, {"idade": 30}, schema) == Marker("idade", 29, 30)


def test_integer_with_no_room_on_either_side_is_dropped() -> None:
    schema = {"idade": Schema(type="integer", maximum=30, minimum=30)}

    assert choose_marker({"idade": 30}, {"idade": 30}, schema) is None


def test_text_comes_before_integer_even_when_the_integer_is_first() -> None:
    marker = choose_marker({"idade": 30, "nome": "Ana"}, {"idade": 30, "nome": "Ana"})

    assert marker is not None
    assert marker.field == "nome"


def test_secret_identifier_privilege_and_audit_names_never_get_the_marker() -> None:
    body: dict[str, JsonValue] = {
        "senha": "x",
        "passwordHash": "x",
        "id": "1",
        "medicoId": "1",
        "userUuid": "u",
        "role": "paciente",
        "plano": "gold",
        "saldo": 5,
        "preco": 9,
        "ativo": 1,
        "ownerId": "9",
        "createdAt": "ontem",
        "requestId": "r",
    }

    assert choose_marker(body, dict(body)) is None


def test_a_field_missing_from_the_reading_cannot_be_confirmed() -> None:
    assert choose_marker({"nome": "Ana"}, {"outro": "x"}) is None


def test_a_field_with_another_type_in_the_reading_is_dropped() -> None:
    assert choose_marker({"nome": "Ana"}, {"nome": 5}) is None
    assert choose_marker({"idade": 30}, {"idade": "30"}) is None


def test_booleans_floats_nulls_lists_and_objects_are_not_markers() -> None:
    body: dict[str, JsonValue] = {"a": True, "b": 1.5, "c": None, "d": [1], "e": {"x": 1}}

    assert choose_marker(body, dict(body)) is None


def test_an_empty_or_non_object_reading_gives_no_marker() -> None:
    assert choose_marker(BODY, {}) is None
    assert choose_marker(BODY, [BEFORE]) is None
    assert choose_marker(BODY, None) is None
    assert choose_marker({}, BEFORE) is None


def test_format_pattern_and_enum_text_fields_are_dropped() -> None:
    for schema in (
        Schema(type="string", format="email"),
        Schema(type="string", pattern="^[A-Z]+$"),
        Schema(type="string", enum=("Ana", "Bia")),
        Schema(type="integer"),
    ):
        assert choose_marker({"nome": "Ana"}, {"nome": "Ana"}, {"nome": schema}) is None
