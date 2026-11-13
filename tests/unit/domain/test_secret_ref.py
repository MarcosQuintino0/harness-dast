import pytest
from pydantic import ValidationError

from harness_dast.domain.secret_ref import SecretRef


@pytest.mark.parametrize(
    "reference", ["env:A", "env:AGENDA_USER_A_SENHA", "env:X9_Y", "env:" + "A" * 128]
)
def test_secret_ref_accepts_when_reference_is_env_name(reference: str) -> None:
    assert SecretRef(secret_ref=reference).secret_ref == reference


def test_env_name_strips_prefix_when_reference_is_valid() -> None:
    assert SecretRef(secret_ref="env:AGENDA_SENHA").env_name  # noqa: S106 - referência, não segredo == "AGENDA_SENHA"


@pytest.mark.parametrize(
    "literal",
    [
        "hunter2",
        "SuperSecret123!",
        "env:",
        "env:lower",
        "env:1STARTS_WITH_DIGIT",
        "env:HAS SPACE",
        "env:HAS-DASH",
        "env:A\n",
        "ENV:ABC",
        "vault:ABC",
        "file:/etc/passwd",
        "env:" + "A" * 129,
        "",
        "eyJhbGciOiJIUzI1NiJ9.payload.sig",
        "${AGENDA_SENHA}",
    ],
)
def test_secret_ref_rejects_when_value_is_not_an_env_reference(literal: str) -> None:
    with pytest.raises(ValidationError, match="env:NOME"):
        SecretRef(secret_ref=literal)


@pytest.mark.parametrize("literal", ["hunter2-LITERAL", "tok3n-LITERAL-abc"])
def test_secret_ref_error_does_not_echo_value_when_literal_is_rejected(literal: str) -> None:
    with pytest.raises(ValidationError) as caught:
        SecretRef(secret_ref=literal)

    assert literal not in str(caught.value)
    assert literal not in repr(caught.value.errors(include_input=False))


@pytest.mark.parametrize(
    "data", [{}, {"secret_ref": None}, {"secret_ref": 5}, {"secret_ref": ["env:A"]}]
)
def test_secret_ref_rejects_when_field_is_missing_or_has_wrong_type(
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SecretRef.model_validate(data)


def test_secret_ref_rejects_extra_fields_when_value_is_added_next_to_reference() -> None:
    with pytest.raises(ValidationError):
        SecretRef.model_validate({"secret_ref": "env:A", "value": "hunter2"})


def test_secret_ref_is_frozen_when_assignment_is_attempted() -> None:
    reference = SecretRef(secret_ref="env:A")  # noqa: S106 - referência, não segredo

    with pytest.raises(ValidationError):
        reference.secret_ref = "env:B"  # type: ignore[misc]  # noqa: S105  # prova que o modelo é congelado
