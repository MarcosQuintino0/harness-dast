"""Plano da atribuição em massa: métodos, leitor do efeito, candidatos e teto (ADR 0040)."""

import json
from typing import Any

from harness_dast.domain.api_model import MediaBody, Operation, RequestBody, SuccessResponse
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.authz_config import AuthzConfig
from harness_dast.domain.authz_plan_mass import (
    count_candidates,
    describe_plan,
    plan_mass_assignment,
)
from harness_dast.domain.probe_exchange import ExchangeRecord

BODY = json.dumps({"nome": "x"})
STR = Schema(type="string")
INT = Schema(type="integer")


def ex(
    op: str,
    method: str = "GET",
    path: str = "/api/x/{id}",
    account: str = "a1",
    target: str | None = None,
    body: str | None = None,
    status: int = 200,
) -> ExchangeRecord:
    return ExchangeRecord(
        operation_id=op,
        method=method,
        path=path,
        target=target or f"/api/x/{op}",
        account=account,
        status=status,
        content_type="application/json" if body else None,
        body=body,
    )


def operation(
    operation_id: str, method: str, path: str, *, returns: dict[str, Schema] | None = None
) -> Operation:
    body = Schema(type="object", properties={"nome": STR})
    request = RequestBody(media=(MediaBody(media_type="application/json", body_schema=body),))
    responses = (
        (SuccessResponse(status="200", body_schema=Schema(type="object", properties=returns)),)
        if returns
        else ()
    )
    return Operation(
        operation_id=operation_id,
        method=method,  # type: ignore[arg-type]
        path=path,
        request_body=request,
        success_responses=responses,
    )


def config(**changes: Any) -> AuthzConfig:
    return AuthzConfig.model_validate(changes)


def plan(items: list[ExchangeRecord], **kwargs: Any) -> Any:
    return plan_mass_assignment(
        items, kwargs.pop("public", frozenset()), kwargs.pop("cfg", config()), **kwargs
    )


def test_the_update_is_paired_with_a_read_of_the_same_path_and_account() -> None:
    items = [
        ex("ler", path="/api/me", target="/api/me"),
        ex("ler_outro", path="/api/me", target="/api/me", account="a2"),
        ex("atualizar", method="PUT", path="/api/me", target="/api/me", body=BODY),
    ]

    result = plan(items)

    assert [
        (t.exchange.operation_id, t.read.operation_id if t.read else None) for t in result.tasks
    ] == [("atualizar", "ler")]


def test_an_update_without_a_read_uses_none() -> None:
    result = plan([ex("up", method="PATCH", path="/api/me", body="{}")])

    assert result.tasks[0].read is None
    assert result.tasks[0].created is False


def test_the_declared_fields_are_the_candidates_when_there_is_no_spec() -> None:
    result = plan([ex("up", method="PUT", path="/api/me", body="{}")])

    assert [c.name for c in result.tasks[0].candidates] == ["role", "papel", "admin", "isAdmin"]
    assert count_candidates(result.tasks) == 4


def test_a_body_that_is_not_a_json_object_or_a_public_or_infrastructure_path_is_not_planned() -> (
    None
):
    items = [
        ex("sem_corpo", method="PUT"),
        ex("lista", method="PUT", body="[1]", path="/p2"),
        ex("quebrado", method="PUT", body="{oops", path="/p3"),
        ex("apaga", method="DELETE", body="{}"),
        ex("pub", method="PUT", body="{}", path="/p4"),
        ex("infra", method="PUT", body="{}", path="/api/saude"),
    ]

    result = plan(items, public=frozenset({"pub"}), infrastructure=frozenset({"/api/saude"}))

    assert result.tasks == ()
    assert {n.operation_id: n.reason for n in result.not_tested} == {
        "sem_corpo": "no_json_body",
        "lista": "no_json_body",
        "quebrado": "no_json_body",
        "pub": "public_operation",
        "infra": "infrastructure_path",
    }


def test_delete_is_never_planned_whatever_the_methods_say() -> None:
    result = plan(
        [ex("apaga", method="DELETE", body="{}")],
        cfg=config(mass_assignment_methods=["PUT", "POST", "PATCH"]),
    )

    assert result.tasks == ()
    assert result.not_tested == ()


def test_only_the_methods_of_the_profile_are_planned() -> None:
    items = [
        ex("put", method="PUT", path="/a", body="{}"),
        ex("patch", method="PATCH", path="/b", body="{}"),
    ]

    result = plan(items, cfg=config(mass_assignment_methods=["PATCH"]))

    assert [t.exchange.operation_id for t in result.tasks] == ["patch"]


def test_a_post_with_a_sibling_get_gets_it_as_reader() -> None:
    post = ex("criar", method="POST", path="/api/medicos", target="/api/medicos", body=BODY)
    read = ex("ler", path="/api/medicos/{id}", target="/api/medicos/9")

    result = plan([post, read])

    task = result.tasks[0]
    assert task.created is True
    assert task.read is not None
    assert task.read.target == "/api/medicos/9"


def test_a_post_reader_must_be_of_the_same_account_and_have_one_final_marker() -> None:
    post = ex("criar", method="POST", path="/api/medicos", target="/api/medicos", body=BODY)
    other_account = ex("ler_b", path="/api/medicos/{id}", account="a2")
    deeper = ex("fundo", path="/api/medicos/{id}/agenda")
    result = plan([post, other_account, deeper])

    assert result.tasks == ()
    assert [n.reason for n in result.not_tested] == ["create_not_readable"]


def test_a_post_without_reader_is_planned_when_the_response_has_a_body_to_look_at() -> None:
    post = ex("criar", method="POST", path="/api/medicos", target="/api/medicos", body=BODY)
    spec = [operation("criar", "post", "/api/medicos", returns={"id": INT, "saldo": INT})]

    result = plan([post], operations=spec)

    assert result.tasks[0].read is None
    assert result.tasks[0].created is True
    assert "saldo" in [c.name for c in result.tasks[0].candidates]


def test_the_candidates_cut_is_noted() -> None:
    returns = {"saldo": INT, "credito": INT, "plano": STR}
    spec = [operation("up", "put", "/api/me", returns=returns)]
    item = ex("up", method="PUT", path="/api/me", body=BODY)

    result = plan([item], cfg=config(max_derived_candidates=1), operations=spec)

    assert [n.reason for n in result.not_tested] == ["candidates_limited"]
    assert "2 campo" in result.not_tested[0].message


def test_the_run_ceiling_leaves_the_operations_that_do_not_fit_for_not_tested() -> None:
    items = [ex(f"op{n}", method="PUT", path=f"/api/r{n}", body=BODY) for n in range(3)]

    result = plan(items, budget=9)

    assert [t.exchange.operation_id for t in result.tasks] == ["op0", "op1"]
    assert [(n.operation_id, n.reason) for n in result.not_tested] == [("op2", "budget_exhausted")]


def test_a_post_of_an_operation_missing_from_the_spec_still_needs_a_reader() -> None:
    post = ex("criar", method="POST", path="/api/medicos", target="/api/medicos", body=BODY)

    result = plan([post], operations=[operation("outra", "get", "/api/x")])

    assert [n.reason for n in result.not_tested] == ["create_not_readable"]


def test_describe_plan_lists_names_and_sources_without_values_and_is_bounded() -> None:
    spec = [operation("up", "put", "/api/me", returns={"saldo": INT})]
    result = plan([ex("up", method="PUT", path="/api/me", body=BODY)], operations=spec)

    text = describe_plan(result.tasks)

    assert text.startswith("PUT /api/me: role, papel, admin, isAdmin, saldo (response_only)")
    assert len(describe_plan(result.tasks * 200)) <= 1500
