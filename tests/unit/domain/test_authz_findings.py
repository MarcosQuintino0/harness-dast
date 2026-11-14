"""Taxonomia dos achados de autorização: severidade, CWE, OWASP e fingerprint."""

import pytest

from harness_dast.domain.authz_finding_build import authz_fingerprint
from harness_dast.domain.authz_findings import (
    TECHNIQUE_LABEL,
    excessive_data_finding,
    horizontal_finding,
    mass_assignment_finding,
    vertical_finding,
)
from harness_dast.domain.authz_result import AuthzResult

ACTOR = ("pac_b", "paciente")
OWNER = ("pac_a", "paciente")


def horizontal(path: str = "/api/consultas/{id}") -> object:
    return horizontal_finding(
        product="p",
        operation_id="ver",
        method="get",
        path_template=path,
        actor=ACTOR,
        owner=OWNER,
        statuses=(200, 200),
    )


def test_horizontal_is_high_and_carries_its_classification() -> None:
    finding = horizontal()

    assert finding.proposed_severity == "high"  # type: ignore[attr-defined]
    assert finding.cwe == 639  # type: ignore[attr-defined]
    assert finding.owasp_api_2023.startswith("API1:2023")  # type: ignore[attr-defined]
    assert finding.origin == "authz"  # type: ignore[attr-defined]
    assert finding.finding_id.startswith("A-")  # type: ignore[attr-defined]


def test_vertical_is_high_with_api5() -> None:
    finding = vertical_finding(
        product="p",
        operation_id="rel",
        method="GET",
        path_template="/api/rel",
        actor=("pac_a", "paciente"),
        owner=("adm", "admin"),
        statuses=(200, 200),
    )

    assert finding.proposed_severity == "high"
    assert finding.owasp_api_2023.startswith("API5:2023")
    assert finding.owner_role == "admin"


def test_excessive_data_is_medium_for_plain_names_and_high_for_secret_names() -> None:
    plain = excessive_data_finding(
        product="p",
        operation_id="l",
        method="GET",
        path_template="/api/x",
        actor=("adm", "admin"),
        status=200,
        fields=("items[].internalNotes",),
    )
    secret = excessive_data_finding(
        product="p",
        operation_id="l",
        method="GET",
        path_template="/api/x",
        actor=("adm", "admin"),
        status=200,
        fields=("items[].internalNotes", "items[].passwordHash"),
    )

    assert plain.proposed_severity == "medium"
    assert secret.proposed_severity == "high"
    assert secret.owasp_api_2023.startswith("API3:2023")
    assert secret.cwe == 213


def test_a_long_field_list_is_shortened_in_the_title_only() -> None:
    fields = tuple(f"campo{i}" for i in range(8))

    finding = excessive_data_finding(
        product="p",
        operation_id="l",
        method="GET",
        path_template="/api/x",
        actor=("adm", "admin"),
        status=200,
        fields=fields,
    )

    assert "e mais 5" in finding.title
    assert finding.fields == fields


@pytest.mark.parametrize(
    ("restored", "text"), [(True, "restaurado"), (False, "Não foi possível"), (None, "Não havia")]
)
def test_mass_assignment_evidence_tells_what_happened_to_the_state(
    restored: bool | None, text: str
) -> None:
    finding = mass_assignment_finding(
        product="p",
        operation_id="up",
        method="PUT",
        path_template="/api/me",
        actor=("pac_a", "paciente"),
        sent_field="role",
        changed=("papel",),
        status=200,
        restored=restored,
    )

    assert text in finding.evidence
    assert finding.proposed_severity == "high"
    assert finding.cwe == 915
    assert finding.fields == ("role", "papel")


def test_the_fingerprint_is_stable_and_ignores_accounts_and_status_codes() -> None:
    first = horizontal()
    other = horizontal_finding(
        product="p",
        operation_id="ver",
        method="GET",
        path_template="/api/consultas/{outroNome}",
        actor=("x", "y"),
        owner=("z", "y"),
        statuses=(200, 204),
    )

    assert first.fingerprint == other.fingerprint  # type: ignore[attr-defined]
    assert first.finding_id == other.finding_id  # type: ignore[attr-defined]


def test_the_fingerprint_changes_with_technique_path_method_product_and_fields() -> None:
    base = dict(
        product="p", technique="authz_horizontal", method="GET", path_template="/a/{id}", fields=()
    )
    reference = authz_fingerprint(**base)  # type: ignore[arg-type]

    variants = [
        {**base, "technique": "authz_vertical"},
        {**base, "path_template": "/b/{id}"},
        {**base, "method": "POST"},
        {**base, "product": "q"},
        {**base, "fields": ("senha",)},
    ]

    assert len({reference, *(authz_fingerprint(**v) for v in variants)}) == 6  # type: ignore[arg-type]


def test_the_fingerprint_does_not_collide_across_field_boundaries() -> None:
    base = dict(product="p", technique="authz_excessive_data", method="GET", path_template="/a")

    one = authz_fingerprint(**base, fields=("ab", "c"))  # type: ignore[arg-type]
    two = authz_fingerprint(**base, fields=("a", "bc"))  # type: ignore[arg-type]

    assert one != two


def test_every_technique_has_a_label() -> None:
    assert set(TECHNIQUE_LABEL) == {
        "authz_horizontal",
        "authz_vertical",
        "authz_excessive_data",
        "authz_mass_assignment",
    }


def test_the_result_model_roundtrips_and_has_no_extra_fields() -> None:
    result = AuthzResult(
        run_id="r",
        product="p",
        status="completed",
        started_at="a",
        finished_at="b",
        findings=(horizontal(),),  # type: ignore[arg-type]
    )

    assert AuthzResult.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValueError, match="extra"):
        AuthzResult.model_validate({**result.model_dump(), "extra": 1})
