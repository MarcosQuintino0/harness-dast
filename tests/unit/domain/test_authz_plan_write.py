"""Plano da escrita em recurso de outra conta (ADR 0042)."""

from collections.abc import Sequence

from harness_dast.domain.api_schema import Schema
from harness_dast.domain.authz_plan_write import (
    MAX_WRITE_TASKS,
    input_properties,
    plan_horizontal_write,
)
from harness_dast.domain.authz_result import AuthzNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.rig import INT, STR, operation, parameter

ROLES = {"a1": "paciente", "a2": "paciente", "boss": "admin"}
BODY = '{"nome":"Ana"}'


def ex(
    op: str,
    method: str = "PUT",
    path: str = "/api/x/{id}",
    target: str = "/api/x/1",
    account: str = "a1",
    body: str | None = BODY,
) -> ExchangeRecord:
    return ExchangeRecord(
        operation_id=op,
        method=method,
        path=path,
        target=target,
        account=account,
        status=200,
        content_type="application/json" if body else None,
        body=body,
    )


READ = ex("ler", "GET", body=None)


def reasons(plan_notes: Sequence[AuthzNotTested]) -> dict[str | None, str]:
    return {n.operation_id: n.reason for n in plan_notes}


def test_put_and_patch_with_an_identifier_a_reader_and_a_peer_enter() -> None:
    items = [READ, ex("put"), ex("patch", "PATCH")]

    plan = plan_horizontal_write(items, ROLES, frozenset())

    assert [(t.exchange.method, t.owner, t.actor, t.read.operation_id) for t in plan.tasks] == [
        ("PUT", ("a1", "paciente"), ("a2", "paciente"), "ler"),
        ("PATCH", ("a1", "paciente"), ("a2", "paciente"), "ler"),
    ]
    assert plan.not_tested == ()


def test_post_delete_get_and_head_are_never_candidates() -> None:
    items = [
        READ,
        ex("cria", "POST"),
        ex("apaga", "DELETE", body=None),
        ex("cabeca", "HEAD", body=None),
    ]

    plan = plan_horizontal_write(items, ROLES, frozenset())

    assert plan.tasks == ()
    assert plan.not_tested == ()


def test_only_one_peer_account_writes() -> None:
    roles = {"a1": "paciente", "a2": "paciente", "a3": "paciente"}

    plan = plan_horizontal_write([READ, ex("put")], roles, frozenset())

    assert [t.actor[0] for t in plan.tasks] == ["a2"]


def test_a_body_that_is_not_a_json_object_is_refused() -> None:
    for body in (None, "[1,2]", "texto", '"x"'):
        plan = plan_horizontal_write([READ, ex("put", body=body)], ROLES, frozenset())

        assert plan.tasks == ()
        assert reasons(plan.not_tested) == {"put": "no_json_body"}


def test_an_operation_without_an_object_identifier_is_refused() -> None:
    item = ex("me", path="/api/me", target="/api/me")

    plan = plan_horizontal_write(
        [ex("lerme", "GET", "/api/me", "/api/me", body=None), item], ROLES, frozenset()
    )

    assert plan.tasks == ()
    assert reasons(plan.not_tested) == {"me": "no_object_identifier"}


def test_an_identifier_in_the_query_enters() -> None:
    op = operation(
        "put",
        "put",
        "/api/x",
        parameters=(parameter("contaId", INT, "query"),),
        body={"nome": STR},
    )
    read = ex("ler", "GET", "/api/x", "/api/x?contaId=7", body=None)
    item = ex("put", path="/api/x", target="/api/x?contaId=7")

    plan = plan_horizontal_write([read, item], ROLES, frozenset(), [op])

    assert len(plan.tasks) == 1
    assert plan.tasks[0].properties == {"nome": STR}


def test_a_public_operation_a_missing_peer_and_a_missing_reader_are_reported() -> None:
    public = plan_horizontal_write([READ, ex("put")], ROLES, frozenset({"put"}))
    alone = plan_horizontal_write(
        [ex("ler", "GET", body=None, account="boss"), ex("put", account="boss")],
        ROLES,
        frozenset(),
    )
    blind = plan_horizontal_write([ex("put")], ROLES, frozenset())

    assert reasons(public.not_tested) == {"put": "public_operation"}
    assert reasons(alone.not_tested) == {"put": "no_peer_account"}
    assert reasons(blind.not_tested) == {"put": "no_read_to_confirm"}


def test_the_reader_must_be_of_the_owner_account() -> None:
    other = ex("ler", "GET", body=None, account="a2")

    plan = plan_horizontal_write([other, ex("put")], ROLES, frozenset())

    assert reasons(plan.not_tested) == {"put": "no_read_to_confirm"}


def test_a_failed_read_in_the_probe_is_not_a_reader() -> None:
    failed = READ.model_copy(update={"status": 500})

    plan = plan_horizontal_write([failed, ex("put")], ROLES, frozenset())

    assert reasons(plan.not_tested) == {"put": "no_read_to_confirm"}


def test_the_budget_caps_the_candidates_and_the_rest_is_reported() -> None:
    items = [
        READ,
        ex("p0", target="/api/x/1"),
        ex("p1", target="/api/x/2"),
        ex("p2", target="/api/x/3"),
    ]

    plan = plan_horizontal_write(items, ROLES, frozenset(), budget=2)

    assert len(plan.tasks) == 2
    assert [n.reason for n in plan.not_tested] == ["budget_exhausted"]
    assert MAX_WRITE_TASKS == 50


def test_an_identical_request_is_planned_once() -> None:
    plan = plan_horizontal_write([READ, ex("put"), ex("put")], ROLES, frozenset())

    assert len(plan.tasks) == 1


def test_input_properties_come_from_the_declared_body_only() -> None:
    declared = operation("put", "put", "/api/x/{id}", body={"nome": STR, "n": INT})
    without = operation("put", "put", "/api/x/{id}")

    assert set(input_properties(declared)) == {"nome", "n"}
    assert input_properties(without) == {}
    assert input_properties(None) == {}
    assert isinstance(input_properties(declared)["nome"], Schema)


def test_shared_role_is_skipped_without_a_write_task() -> None:
    plan = plan_horizontal_write([READ, ex("put")], ROLES, frozenset(), shared_roles=("paciente",))
    assert plan.tasks == ()
    assert reasons(plan.not_tested) == {"put": "shared_role"}
