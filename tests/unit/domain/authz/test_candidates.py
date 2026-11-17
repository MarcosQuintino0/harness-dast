"""Candidatos de campo proibido e valor de teste (ADR 0040)."""

from typing import Any

import pytest

from harness_dast.domain.api_model import MediaBody, Operation, RequestBody, SuccessResponse
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.authz.candidates import (
    POST_MAX_CANDIDATES,
    build_candidates,
    family_key,
    family_of,
    mass_severity,
    path_tail,
)
from harness_dast.domain.authz.config import AuthzConfig

STR = Schema(type="string")
INT = Schema(type="integer")
BOOL = Schema(type="boolean")


def obj(**properties: Schema) -> Schema:
    return Schema(type="object", properties=properties)


def op(
    operation_id: str,
    method: str,
    path: str,
    *,
    body: Schema | None = None,
    returns: Schema | None = None,
) -> Operation:
    request = (
        RequestBody(media=(MediaBody(media_type="application/json", body_schema=body),))
        if body is not None
        else None
    )
    responses = (SuccessResponse(status="200", body_schema=returns),) if returns else ()
    return Operation(
        operation_id=operation_id,
        method=method,  # type: ignore[arg-type]
        path=path,
        request_body=request,
        success_responses=responses,
    )


def config(**changes: Any) -> AuthzConfig:
    return AuthzConfig.model_validate({"mass_assignment_fields": [], **changes})


def names(plan: Any) -> list[tuple[str, str]]:
    return [(item.name, item.source) for item in plan.candidates]


# --- família ------------------------------------------------------------------------------


def test_the_collection_and_the_item_are_the_same_family() -> None:
    assert family_key("/api/medicos") == family_key("/api/medicos/{id}")


def test_a_path_with_a_marker_in_the_middle_does_not_join_the_collection() -> None:
    assert family_key("/a/{x}/b") != family_key("/a")
    assert family_key("/a/{x}/b") == family_key("/a/{y}/b")


def test_family_of_returns_only_the_operations_of_the_same_resource() -> None:
    post = op("criar", "post", "/api/medicos")
    read = op("ler", "get", "/api/medicos/{id}")
    other = op("outro", "get", "/api/pacientes")

    assert family_of(post, [post, read, other]) == (post, read)


def test_the_path_tail_skips_markers() -> None:
    assert path_tail("/api/medicos/{id}") == "medicos"
    assert path_tail("/{id}") is None


# --- origens ------------------------------------------------------------------------------


def test_a_field_only_in_the_response_is_a_response_only_candidate() -> None:
    put = op("up", "put", "/api/me", body=obj(nome=STR), returns=obj(nome=STR, nivel=STR))

    plan = build_candidates(put, [put], config())

    assert names(plan) == [("nivel", "response_only")]


def test_a_read_only_field_in_the_input_is_a_readonly_candidate() -> None:
    body = obj(nome=STR, plano=Schema(type="string", read_only=True))
    put = op("up", "put", "/api/me", body=body)

    assert names(build_candidates(put, [put], config())) == [("plano", "readonly_in_input")]


def test_a_privilege_name_in_the_input_is_a_name_in_input_candidate() -> None:
    put = op("up", "put", "/api/me", body=obj(nome=STR, role=STR))

    assert names(build_candidates(put, [put], config())) == [("role", "name_in_input")]


@pytest.mark.parametrize("name", ["valor", "price", "saldo", "ativo", "nome"])
def test_a_non_privilege_field_the_input_already_declares_is_not_a_candidate(name: str) -> None:
    post = op(
        "criar", "post", "/api/consultas", body=obj(**{name: INT}), returns=obj(**{name: INT})
    )

    assert names(build_candidates(post, [post], config(), post=True)) == []


def test_a_field_in_both_without_a_privilege_name_is_not_a_candidate() -> None:
    put = op("up", "put", "/api/me", body=obj(nome=STR), returns=obj(nome=STR))

    assert build_candidates(put, [put], config()).candidates == ()


def test_the_response_of_the_family_counts_and_the_list_item_is_used() -> None:
    post = op("criar", "post", "/api/medicos", body=obj(nome=STR))
    listing = op(
        "listar",
        "get",
        "/api/medicos",
        returns=Schema(type="array", items=obj(id=INT, nome=STR, saldo=INT)),
    )

    plan = build_candidates(post, family_of(post, [post, listing]), config())

    assert names(plan) == [("saldo", "response_only")]


def test_a_pagination_envelope_does_not_leak_its_control_fields() -> None:
    envelope = obj(items=Schema(type="array", items=obj(nome=STR, saldo=INT)), limit=INT)
    post = op("criar", "post", "/api/medicos", body=obj(nome=STR))
    listing = op("listar", "get", "/api/medicos", returns=envelope)

    plan = build_candidates(post, family_of(post, [post, listing]), config())

    assert names(plan) == [("saldo", "response_only")]


def test_the_declared_name_wins_over_the_derived_one_in_any_spelling() -> None:
    put = op("up", "put", "/api/me", body=obj(nome=STR), returns=obj(is_admin=BOOL))
    declared = config(mass_assignment_fields=[{"name": "isAdmin", "value": True}])

    plan = build_candidates(put, [put], declared)

    assert names(plan) == [("isAdmin", "declared")]


def test_declared_fields_come_first_in_the_declared_order() -> None:
    put = op("up", "put", "/api/me", body=obj(nome=STR), returns=obj(saldo=INT))
    declared = config(
        mass_assignment_fields=[{"name": "zeta", "value": 1}, {"name": "alfa", "value": 1}]
    )

    assert [i.name for i in build_candidates(put, [put], declared).candidates] == [
        "zeta",
        "alfa",
        "saldo",
    ]


# --- exclusões ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "excluded",
    ["passwordHash", "id", "createdAt", "version", "ownerId", "tenantId", "medicoId"],
)
def test_secret_identifier_audit_and_ownership_names_are_never_derived(excluded: str) -> None:
    post = op("criar", "post", "/api/medicos", returns=obj(**{excluded: STR}))

    assert build_candidates(post, [post], config()).candidates == ()


def test_objects_and_lists_are_never_derived() -> None:
    returns = obj(endereco=obj(rua=STR), tags=Schema(type="array", items=STR), saldo=INT)
    put = op("up", "put", "/api/me", body=obj(nome=STR), returns=returns)

    assert names(build_candidates(put, [put], config())) == [("saldo", "response_only")]


def test_a_field_without_a_known_name_is_only_other_and_goes_last() -> None:
    put = op("up", "put", "/api/me", body=obj(nome=STR), returns=obj(apelido=STR, saldo=INT))

    plan = build_candidates(put, [put], config())

    assert [(i.name, i.kind) for i in plan.candidates] == [
        ("saldo", "balance"),
        ("apelido", "other"),
    ]


def test_ownership_is_only_tested_when_declared() -> None:
    put = op("up", "put", "/api/me", body=obj(nome=STR), returns=obj(ownerId=INT))
    declared = config(mass_assignment_fields=[{"name": "ownerId", "value": 2}])

    assert build_candidates(put, [put], config()).candidates == ()
    assert names(build_candidates(put, [put], declared)) == [("ownerId", "declared")]


# --- limite e determinismo ----------------------------------------------------------------


def test_the_derived_limit_cuts_and_counts_what_was_cut() -> None:
    returns = obj(saldo=INT, credito=INT, plano=STR, preco=INT)
    put = op("up", "put", "/api/me", body=obj(nome=STR), returns=returns)

    plan = build_candidates(put, [put], config(max_derived_candidates=2))

    assert [i.name for i in plan.candidates] == ["plano", "credito"]
    assert plan.cut == 2


def test_two_calls_give_the_same_order() -> None:
    returns = obj(saldo=INT, plano=STR, preco=INT, apelido=STR, ativo=BOOL)
    put = op("up", "put", "/api/me", body=obj(nome=STR), returns=returns)

    assert build_candidates(put, [put], config()) == build_candidates(put, [put], config())


def test_derivation_off_or_unknown_operation_keeps_only_the_declared_fields() -> None:
    put = op("up", "put", "/api/me", body=obj(nome=STR), returns=obj(saldo=INT))
    declared = [{"name": "role", "value": "admin"}]

    off = build_candidates(
        put, [put], config(derive_mass_candidates=False, mass_assignment_fields=declared)
    )
    unknown = build_candidates(None, [], config(mass_assignment_fields=declared))

    assert names(off) == names(unknown) == [("role", "declared")]


def test_a_post_keeps_only_known_classes_and_at_most_four_derived() -> None:
    returns = obj(saldo=INT, credito=INT, plano=STR, preco=INT, nivel=STR, apelido=STR)
    post = op("criar", "post", "/api/medicos", body=obj(nome=STR), returns=returns)

    plan = build_candidates(post, [post], config(max_derived_candidates=20), post=True)

    assert len(plan.candidates) == POST_MAX_CANDIDATES
    assert all(item.kind != "other" for item in plan.candidates)
    assert plan.cut == 1


def test_a_schema_with_composition_and_an_empty_one_do_not_break() -> None:
    returns = Schema(all_of=(obj(saldo=INT), obj(plano=STR)))
    put = op("up", "put", "/api/me", body=Schema(), returns=returns)

    assert {i.name for i in build_candidates(put, [put], config()).candidates} == {"saldo", "plano"}


# --- severidade ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "kind", "severity"),
    [
        ("declared", "other", "high"),
        ("declared", "price", "high"),
        ("response_only", "privilege", "high"),
        ("response_only", "balance", "high"),
        ("response_only", "price", "medium"),
        ("readonly_in_input", "state", "medium"),
        ("name_in_input", "other", "medium"),
    ],
)
def test_severity_depends_on_the_class(source: Any, kind: Any, severity: str) -> None:
    assert mass_severity(source, kind) == severity
