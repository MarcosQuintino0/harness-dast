"""Taxonomia dos achados de autorização: severidade, CWE, OWASP e fingerprint."""

from typing import Any

import pytest

from harness_dast.domain.api_model import Operation, SecurityRequirement
from harness_dast.domain.authz_finding_build import authz_fingerprint
from harness_dast.domain.authz_findings import (
    TECHNIQUE_LABEL,
    excessive_data_finding,
    horizontal_finding,
    mass_assignment_finding,
    vertical_finding,
)
from harness_dast.domain.authz_findings_access import anonymous_finding, tampered_finding
from harness_dast.domain.authz_findings_write import horizontal_write_finding
from harness_dast.domain.authz_identifiers import IdentifierRef
from harness_dast.domain.authz_result import AuthzFinding, AuthzResult

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


def test_a_mass_assignment_finding_does_not_repeat_the_sent_field_in_fields() -> None:
    finding = mass_assignment_finding(
        product="p",
        operation_id="criar",
        method="POST",
        path_template="/api/consultas",
        actor=("admin", "admin"),
        sent_field="valor",
        changed=("valor",),
        status=201,
        restored=None,
    )

    assert finding.fields == ("valor",)


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
        "authz_anonymous_access",
        "authz_tampered_token",
        "authz_mass_assignment",
        "authz_horizontal_write",
        "authz_access_matrix",
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


# --- acesso sem login e token adulterado (ADR 0039) ---------------------------------------------

REQUIRED = Operation(
    operation_id="ver",
    method="get",
    path="/api/x",
    security=(SecurityRequirement(schemes=("bearer",)),),
)
UNDECLARED = Operation(operation_id="ver", method="get", path="/api/x")


def anonymous(operation: Operation | None = REQUIRED) -> AuthzFinding:
    return anonymous_finding(
        product="p",
        operation_id="ver",
        method="get",
        path_template="/api/x",
        actor=ACTOR,
        operation=operation,
        statuses=(200, 200),
    )


def tampered(variants: tuple[str, ...] = ("alg_none",)) -> AuthzFinding:
    return tampered_finding(
        product="p",
        operation_id="ver",
        method="get",
        path_template="/api/x",
        actor=ACTOR,
        variants=variants,  # type: ignore[arg-type]
        statuses=(200, 200),
    )


def test_anonymous_access_is_high_when_the_openapi_requires_authentication() -> None:
    finding = anonymous()

    assert finding.proposed_severity == "high"
    assert finding.cwe == 306
    assert finding.owasp_api_2023 == "API2:2023 Broken Authentication"
    assert finding.technique == "authz_anonymous_access"
    assert finding.owner_account is None
    assert finding.variants == ()


def test_anonymous_access_is_medium_and_asks_for_triage_when_security_is_undeclared() -> None:
    finding = anonymous(UNDECLARED)

    assert finding.proposed_severity == "medium"
    assert "public_operations" in finding.evidence


def test_tampered_token_is_always_high_with_cwe_by_variant() -> None:
    jwt = tampered(("stripped_signature", "scrambled"))
    only_text = tampered(("scrambled",))

    assert jwt.proposed_severity == only_text.proposed_severity == "high"
    assert jwt.cwe == 347
    assert only_text.cwe == 287
    assert jwt.variants == ("stripped_signature", "scrambled")
    assert jwt.owasp_api_2023.startswith("API2:2023")


def test_the_tampered_fingerprint_ignores_the_variants_and_the_cwe() -> None:
    one = tampered(("alg_none",))
    other = tampered(("scrambled",))

    assert one.fingerprint == other.fingerprint
    assert one.finding_id == other.finding_id
    assert one.finding_id.startswith("A-")
    assert len(one.finding_id) == 10


def test_the_two_techniques_never_share_a_fingerprint_for_the_same_operation() -> None:
    assert anonymous().fingerprint != tampered().fingerprint


def test_access_findings_carry_no_token_text() -> None:
    text = anonymous().model_dump_json() + tampered().model_dump_json()

    assert "Bearer" not in text
    assert "eyJ" not in text


def mass(source: Any, kind: Any, method: str = "PUT") -> AuthzFinding:
    return mass_assignment_finding(
        product="p",
        operation_id="up",
        method=method,
        path_template="/api/me",
        actor=("pac_a", "paciente"),
        sent_field="saldo",
        changed=("saldo",),
        status=200,
        restored=None if method == "POST" else True,
        source=source,
        kind=kind,
        observed_in="created_read" if method == "POST" else "update",
    )


def test_the_mass_finding_carries_its_source_and_names_it_in_title_and_evidence() -> None:
    declared = mass("declared", "balance")
    derived = mass("response_only", "balance")

    assert declared.candidate_source == "declared"
    assert "OpenAPI" not in declared.title
    assert derived.candidate_source == "response_only"
    assert "campo tirado do OpenAPI" in derived.title
    assert "só mostra na resposta" in derived.evidence


@pytest.mark.parametrize(
    ("source", "kind", "severity"),
    [
        ("declared", "other", "high"),
        ("response_only", "privilege", "high"),
        ("readonly_in_input", "balance", "high"),
        ("response_only", "price", "medium"),
        ("name_in_input", "state", "medium"),
        ("response_only", "other", "medium"),
    ],
)
def test_the_mass_severity_follows_the_class(source: Any, kind: Any, severity: str) -> None:
    assert mass(source, kind).proposed_severity == severity


def test_a_post_finding_says_the_created_resource_stays_and_where_it_was_seen() -> None:
    finding = mass("response_only", "privilege", method="POST")

    assert "continua no ambiente" in finding.evidence
    assert "leitura do recurso criado" in finding.evidence
    assert "ao criar o recurso" in finding.evidence


def test_the_source_does_not_change_the_fingerprint() -> None:
    assert mass("declared", "balance").fingerprint == mass("response_only", "price").fingerprint


# --- ADR 0042: identificador de consulta e escrita em outra conta -------------------------

PATH_ID_FINGERPRINT = "985246a245906dcc884b74ebcc4d38a87effbcf66c984748af08b2f59b6e61e1"
"""Fingerprint do achado horizontal de caminho, calculado antes da versão 1.4: não pode mudar."""


def path_finding() -> AuthzFinding:
    return horizontal_finding(
        product="clinica",
        operation_id="buscarConsulta",
        method="GET",
        path_template="/api/consultas/{id}",
        actor=("b", "p"),
        owner=("a", "p"),
        statuses=(200, 200),
    )


def query_finding(confidence: str) -> AuthzFinding:
    return horizontal_finding(
        product="clinica",
        operation_id="listar",
        method="GET",
        path_template="/api/consultas",
        actor=("b", "p"),
        owner=("a", "p"),
        statuses=(200, 200),
        identifiers=(IdentifierRef("query", "pacienteId", confidence),),  # type: ignore[arg-type]
    )


def test_a_path_identifier_keeps_empty_fields_and_the_fingerprint_from_before() -> None:
    finding = path_finding()

    assert finding.fields == ()
    assert finding.fingerprint == PATH_ID_FINGERPRINT
    assert finding.proposed_severity == "high"
    assert finding.title.endswith("do mesmo papel")


def test_a_query_identifier_goes_to_fields_and_gives_another_fingerprint() -> None:
    finding = query_finding("owned_hint")

    assert finding.fields == ("query:pacienteId",)
    assert finding.fingerprint != PATH_ID_FINGERPRINT
    assert "Identificador na consulta: `pacienteId`" in finding.evidence
    assert "identificador de caminho da conta dona" in finding.evidence
    assert "(identificador na consulta)" in finding.title


def test_the_same_operation_with_path_and_query_ids_is_two_distinct_findings() -> None:
    both = horizontal_finding(
        product="clinica",
        operation_id="buscarConsulta",
        method="GET",
        path_template="/api/consultas/{id}",
        actor=("b", "p"),
        owner=("a", "p"),
        statuses=(200, 200),
        identifiers=(IdentifierRef("query", "medicoId", "name_only"),),
    )

    assert both.fingerprint != path_finding().fingerprint
    assert both.proposed_severity == "high"  # o caminho decide


def test_severity_of_a_query_identifier_depends_on_the_confidence() -> None:
    assert query_finding("owned_hint").proposed_severity == "high"
    name_only = query_finding("name_only")
    assert name_only.proposed_severity == "medium"
    assert "só o nome indica identificador" in name_only.evidence


def test_the_write_finding_is_high_names_the_field_and_never_a_value() -> None:
    finding = horizontal_write_finding(
        product="clinica",
        operation_id="salvarNota",
        method="put",
        path_template="/api/notas/{id}",
        actor=("b", "p"),
        owner=("a", "p"),
        status=200,
        field="titulo",
        restored=True,
    )

    assert finding.technique == "authz_horizontal_write"
    assert (finding.proposed_severity, finding.cwe) == ("high", 639)
    assert finding.owasp_api_2023 == "API1:2023 Broken Object Level Authorization"
    assert (finding.fields, finding.method, finding.observed_status) == (("titulo",), "PUT", 200)
    assert (finding.actor_account, finding.owner_account) == ("b", "a")
    assert "campo `titulo`" in finding.evidence
    assert "restaurado" in finding.evidence


def test_the_write_finding_says_when_the_value_was_not_restored() -> None:
    finding = horizontal_write_finding(
        product="clinica",
        operation_id="salvarNota",
        method="PATCH",
        path_template="/api/notas/{id}",
        actor=("b", "p"),
        owner=("a", "p"),
        status=204,
        field="titulo",
        restored=False,
    )

    assert "NÃO pôde ser restaurado" in finding.evidence


def test_the_write_fingerprint_depends_on_the_field_and_not_on_accounts() -> None:
    def build(field: str, actor: str) -> AuthzFinding:
        return horizontal_write_finding(
            product="clinica",
            operation_id="salvarNota",
            method="PUT",
            path_template="/api/notas/{id}",
            actor=(actor, "p"),
            owner=("a", "p"),
            status=200,
            field=field,
            restored=True,
        )

    assert build("titulo", "b").fingerprint == build("titulo", "c").fingerprint
    assert build("titulo", "b").fingerprint != build("ordem", "b").fingerprint
