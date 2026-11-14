"""Valor de teste dos candidatos da atribuição em massa (ADR 0040)."""

from typing import Any

import pytest

from harness_dast.domain.api_schema import Schema
from harness_dast.domain.authz_candidates import Candidate
from harness_dast.domain.authz_fields import classify_candidate
from harness_dast.domain.authz_test_value import pick_test_value

STR = Schema(type="string")
INT = Schema(type="integer")
BOOL = Schema(type="boolean")


# --- valor de teste -----------------------------------------------------------------------


def cand(name: str, schema: Schema | None, kind: Any = None, **extra: Any) -> Candidate:
    return Candidate(
        name=name,
        source="response_only",
        kind=kind or classify_candidate(name) or "other",
        schema=schema,
        **extra,
    )


def test_a_declared_value_is_used_as_declared() -> None:
    declared = Candidate(name="x", source="declared", kind="other", declared_value=7)

    assert pick_test_value(declared, 3).value == 7


def test_a_privilege_boolean_goes_true_and_skips_when_already_true() -> None:
    assert pick_test_value(cand("isAdmin", BOOL), False).value is True
    assert pick_test_value(cand("isAdmin", BOOL), None).value is True
    assert pick_test_value(cand("isAdmin", BOOL), True).skip == "already_in_target_state"


def test_a_bad_state_boolean_goes_false_never_toward_locking_the_account() -> None:
    assert pick_test_value(cand("blocked", BOOL), True).value is False
    assert pick_test_value(cand("blocked", BOOL), False).skip == "already_in_target_state"
    assert pick_test_value(cand("isActive", BOOL), False).value is True


def test_a_boolean_of_an_unknown_class_is_not_guessed() -> None:
    assert pick_test_value(cand("apelido", BOOL), None).skip == "no_safe_test_value"


def test_numbers_move_one_step_in_the_direction_of_the_name() -> None:
    assert pick_test_value(cand("saldo", INT), 10).value == 11
    assert pick_test_value(cand("preco", INT), 10).value == 9
    assert pick_test_value(cand("discount", INT), 10).value == 11
    assert pick_test_value(cand("saldo", INT), None).value == 1


def test_a_number_at_the_maximum_has_no_safe_value() -> None:
    schema = Schema(type="integer", maximum=10)

    assert pick_test_value(cand("saldo", schema), 10).skip == "no_safe_test_value"


def test_a_number_below_the_minimum_is_raised_to_it() -> None:
    schema = Schema(type="integer", minimum=5)

    assert pick_test_value(cand("saldo", schema), None).value == 5


def test_exclusive_bounds_step_inside() -> None:
    schema = Schema(type="integer", minimum=0, exclusive_minimum=True)

    assert pick_test_value(cand("preco", schema), 1).skip == "no_safe_test_value"
    assert pick_test_value(cand("preco", schema), None).value == 1


def test_an_integer_field_with_a_fractional_current_value_is_skipped() -> None:
    assert pick_test_value(cand("saldo", INT), 1.5).skip == "no_safe_test_value"


def test_a_number_field_keeps_a_float() -> None:
    assert pick_test_value(cand("saldo", Schema(type="number")), 1.5).value == 2.5


def test_a_number_of_the_wrong_class_is_skipped() -> None:
    assert pick_test_value(cand("apelido", INT), 1).skip == "no_safe_test_value"


def test_an_enum_picks_the_first_different_value_and_prefers_admin_for_privilege() -> None:
    enum = Schema(type="string", enum=("paciente", "medico", "ADMIN"))

    assert pick_test_value(cand("papel", enum), "paciente").value == "ADMIN"
    assert (
        pick_test_value(cand("categoria", Schema(type="string", enum=("a", "b"))), "a").value == "b"
    )


def test_an_enum_with_nothing_different_or_empty_has_no_safe_value() -> None:
    assert pick_test_value(cand("papel", Schema(type="string", enum=("x",))), "x").skip == (
        "no_safe_test_value"
    )
    assert pick_test_value(cand("papel", Schema(type="string", enum=())), None).skip == (
        "no_safe_test_value"
    )


def test_a_state_enum_never_picks_a_value_that_locks_the_account() -> None:
    enum = Schema(type="string", enum=("blocked", "suspended", "ativo"))

    assert pick_test_value(cand("ativo", enum), "ativo").skip == "no_safe_test_value"
    assert pick_test_value(cand("ativo", enum), "blocked").value == "ativo"


def test_text_gets_admin_for_privilege_and_a_marker_for_the_others() -> None:
    assert pick_test_value(cand("plano", STR), "basico").value == "admin"
    assert pick_test_value(cand("apelido", STR), None).value == "hdast-teste"


def test_text_is_cut_to_max_length_and_skipped_when_it_cannot_fit() -> None:
    assert (
        pick_test_value(cand("apelido", Schema(type="string", max_length=4)), None).value == "hdas"
    )
    assert pick_test_value(cand("apelido", Schema(type="string", max_length=0)), None).skip == (
        "no_safe_test_value"
    )
    assert (
        pick_test_value(cand("apelido", Schema(type="string", min_length=20)), None).skip
        == "no_safe_test_value"
    )


@pytest.mark.parametrize(
    "schema", [Schema(type="string", format="uuid"), Schema(type="string", pattern="^a$")]
)
def test_text_with_format_or_pattern_is_skipped(schema: Schema) -> None:
    assert pick_test_value(cand("apelido", schema), None).skip == "no_safe_test_value"


@pytest.mark.parametrize("schema", [None, Schema(), Schema(type="object"), Schema(type="null")])
def test_an_unknown_or_non_scalar_schema_is_skipped(schema: Schema | None) -> None:
    assert pick_test_value(cand("saldo", schema), 1).skip == "no_safe_test_value"
