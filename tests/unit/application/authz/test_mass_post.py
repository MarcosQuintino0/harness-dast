"""`authz`: atribuição em massa num `POST` que cria recurso (ADR 0040)."""

from typing import Any

from harness_dast.application.authz.service import AuthzRequest
from harness_dast.domain.authz.result import AuthzNotTested, AuthzResult
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.profile import ProductProfile
from tests.fakes.authz.rig import AuthzRig, Clinic, clinic_profile_data, clinic_spec

POST_ONLY: dict[str, Any] = {
    "mass_assignment_methods": ["POST"],
    "mass_assignment_fields": [],
}


def post_rig(clinic: Clinic, **authz: Any) -> AuthzRig:
    return AuthzRig(clinic, spec=clinic_spec(derived=True), authz={**POST_ONLY, **authz})


def run_mass(rig: AuthzRig) -> AuthzResult:
    probe = rig.run_probe()
    return rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )


def notes(result: AuthzResult, reason: str) -> list[AuthzNotTested]:
    return [n for n in result.not_tested if n.reason == reason]


def authz_requests(rig: AuthzRig, method: str) -> list[HttpRequest]:
    return [
        r for r in rig.target.requests if r.method == method and r.operation_id.startswith("authz:")
    ]


def test_a_post_with_location_reads_the_created_resource_and_reports_the_finding() -> None:
    rig = post_rig(Clinic(creates=("nivelAcesso", "ativo")))

    result = run_mass(rig)

    found = {f.fields[0]: f for f in result.findings}
    assert set(found) == {"nivelAcesso", "ativo"}
    assert found["nivelAcesso"].method == "POST"
    assert found["nivelAcesso"].candidate_source == "response_only"
    assert "leitura do recurso criado" in found["nivelAcesso"].evidence
    assert "continua no ambiente" in found["nivelAcesso"].evidence
    assert [r.url.rsplit("/", 1)[1] for r in authz_requests(rig, "GET")] == ["2", "3"]
    assert result.created_resources == 2
    assert result.effects == ()  # efeito de atribuição em massa é achado, não recibo reutilizável


def test_a_post_creates_one_resource_per_candidate_and_never_deletes() -> None:
    rig = post_rig(Clinic(creates=("nivelAcesso", "ativo")))

    result = run_mass(rig)

    assert len(authz_requests(rig, "POST")) == 2
    assert len(rig.clinic.medicos) == result.created_resources + 1  # +1: o POST do probe
    assert all(r.method != "DELETE" for r in rig.target.requests)


def test_a_post_without_location_uses_the_id_in_the_body() -> None:
    rig = post_rig(Clinic(creates=("nivelAcesso",), location="none"))

    result = run_mass(rig)

    assert [f.fields[0] for f in result.findings] == ["nivelAcesso"]
    assert "leitura do recurso criado" in result.findings[0].evidence


def test_an_absolute_location_on_the_same_base_url_is_accepted() -> None:
    rig = post_rig(Clinic(creates=("nivelAcesso",), location="absolute", id_in_body=False))

    result = run_mass(rig)

    assert [f.fields[0] for f in result.findings] == ["nivelAcesso"]
    assert "leitura do recurso criado" in result.findings[0].evidence


def test_a_location_on_another_host_is_ignored_and_the_body_id_is_used() -> None:
    rig = post_rig(Clinic(creates=("nivelAcesso",), location="other_host"))

    result = run_mass(rig)

    assert all("outro.example.org" not in r.url for r in rig.target.requests)
    assert [f.fields[0] for f in result.findings] == ["nivelAcesso"]
    assert "leitura do recurso criado" in result.findings[0].evidence


def test_when_the_created_read_fails_the_post_echo_is_not_proof() -> None:
    rig = post_rig(Clinic(creates=("nivelAcesso",), post_echo=True))
    probe = rig.run_probe()
    rig.clinic.readable = False

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )

    assert not result.findings
    assert notes(result, "effect_unobservable")
    assert result.effects == ()


def test_a_traversal_location_never_becomes_a_request() -> None:
    rig = post_rig(
        Clinic(creates=("nivelAcesso",), location="traversal", id_in_body=False, post_echo=True)
    )

    run_mass(rig)

    assert all(".." not in r.url for r in rig.target.requests)


def test_a_post_without_reader_and_without_echo_is_unobservable_and_stops_the_operation() -> None:
    rig = post_rig(Clinic(creates=("nivelAcesso", "ativo"), location="none", id_in_body=False))

    result = run_mass(rig)

    assert result.findings == ()
    found = notes(result, "effect_unobservable")
    assert len(found) == 1
    assert "recurso foi criado" in found[0].message
    assert len(authz_requests(rig, "POST")) == 1


def test_a_post_with_no_sibling_get_and_no_response_body_is_not_readable() -> None:
    spec = clinic_spec(derived=True)
    kept = [op for op in spec.operations if op.operation_id != "lerMedico"]
    bare = [
        op.model_copy(update={"success_responses": ()}) if op.operation_id == "criarMedico" else op
        for op in kept
    ]
    rig = AuthzRig(
        Clinic(creates=("nivelAcesso",)),
        spec=spec.model_copy(update={"operations": tuple(bare)}),
        authz=POST_ONLY,
    )

    result = run_mass(rig)

    assert len(notes(result, "create_not_readable")) == 1
    assert authz_requests(rig, "POST") == []


def test_a_conflict_becomes_create_conflict_with_a_hint_and_stops_the_operation() -> None:
    rig = post_rig(Clinic(creates=("nivelAcesso", "ativo")))
    probe = rig.run_probe()
    rig.clinic.conflict = True

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )

    found = notes(result, "create_conflict")
    assert len(found) == 1
    assert "data-rules.yml" in found[0].message
    assert len(authz_requests(rig, "POST")) == 1
    assert result.created_resources == 0


def test_the_post_candidates_are_limited_to_four_derived_plus_the_declared() -> None:
    rig = post_rig(
        Clinic(creates=("nivelAcesso",)),
        mass_assignment_fields=[{"name": "isAdmin", "value": True}],
        max_derived_candidates=20,
    )

    result = run_mass(rig)

    sent = [r.body or b"" for r in authz_requests(rig, "POST")]
    assert any(b"isAdmin" in body for body in sent)
    assert len(sent) <= 5
    assert result.created_resources == len(sent)


def test_a_post_is_not_tested_when_the_profile_removes_post_from_the_methods() -> None:
    rig = post_rig(Clinic(creates=("nivelAcesso",)), mass_assignment_methods=["PUT"])

    run_mass(rig)

    assert authz_requests(rig, "POST") == []


def test_the_created_read_goes_through_the_scope_guard_and_deny_paths_stops_it() -> None:
    data = clinic_profile_data(**POST_ONLY)
    data["scope"]["deny_paths"] = [*data["scope"].get("deny_paths", []), "/api/medicos/2"]
    rig = AuthzRig(
        Clinic(creates=("nivelAcesso",), post_echo=True),
        profile=ProductProfile.from_data(data),
        spec=clinic_spec(derived=True),
    )

    result = run_mass(rig)

    assert all(not r.url.endswith("/api/medicos/2") for r in rig.target.requests)
    assert not result.findings
    assert any(n.reason == "effect_unobservable" for n in result.not_tested)
