"""Plano do teste de autorização: o que repetir, com qual conta, e o que fica sem teste."""

import json

from harness_dast.domain.authz_plan import (
    MAX_PEERS,
    plan_excessive,
    plan_horizontal,
    plan_mass_assignment,
    plan_vertical,
)
from harness_dast.domain.probe_exchange import ExchangeRecord

ROLES = {"a1": "paciente", "a2": "paciente", "a3": "paciente", "boss": "admin", "doc": "medico"}
ORDER = ("paciente", "medico", "admin")


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


# --- horizontal -----------------------------------------------------------------------------


def test_horizontal_picks_the_peers_of_the_same_role_only() -> None:
    plan = plan_horizontal([ex("ver")], ROLES, frozenset())

    assert [(t.owner, t.actor) for t in plan.tasks] == [
        (("a1", "paciente"), ("a2", "paciente")),
        (("a1", "paciente"), ("a3", "paciente")),
    ]
    assert len(plan.tasks) <= MAX_PEERS


def test_horizontal_skips_public_collections_and_writes() -> None:
    items = [
        ex("pub"),
        ex("lista", path="/api/x", target="/api/x"),
        ex("grava", method="POST", path="/api/x/{id}"),
    ]

    plan = plan_horizontal(items, ROLES, frozenset({"pub"}))

    assert plan.tasks == ()
    assert {n.operation_id: n.reason for n in plan.not_tested} == {
        "pub": "public_operation",
        "lista": "no_path_parameter",
    }


def test_horizontal_reports_a_role_with_a_single_account() -> None:
    plan = plan_horizontal([ex("ver", account="boss")], ROLES, frozenset())

    assert plan.tasks == ()
    assert plan.not_tested[0].reason == "no_peer_account"
    assert "admin" in plan.not_tested[0].message


def test_horizontal_an_unknown_owner_account_is_not_tested() -> None:
    plan = plan_horizontal([ex("ver", account="fantasma")], ROLES, frozenset())

    assert plan.not_tested[0].reason == "no_peer_account"


def test_horizontal_does_not_repeat_the_same_request_twice() -> None:
    plan = plan_horizontal([ex("ver"), ex("ver")], ROLES, frozenset())

    assert len(plan.tasks) == 2  # dois pares, não quatro


def test_horizontal_never_invents_a_target() -> None:
    plan = plan_horizontal([ex("ver", target="/api/x/42")], ROLES, frozenset())

    assert {t.exchange.target for t in plan.tasks} == {"/api/x/42"}


# --- excessivo ------------------------------------------------------------------------------


def test_excessive_considers_every_get_only() -> None:
    items = [ex("a"), ex("b", method="POST"), ex("c", path="/api/c", target="/api/c")]

    assert [e.operation_id for e in plan_excessive(items).tasks] == ["a", "c"]


# --- vertical -------------------------------------------------------------------------------


def assigned_to(*pairs: tuple[str, str]):  # type: ignore[no-untyped-def]  # fábrica de teste
    table = dict(pairs)
    return lambda item: table.get(item.operation_id)


def test_vertical_repeats_with_one_account_of_each_lower_role() -> None:
    items = [ex("rel", path="/api/rel", target="/api/rel", account="boss")]

    plan = plan_vertical(
        items, ROLES, ORDER, assigned_to(("rel", "boss")), frozenset({"GET"}), frozenset()
    )

    assert [t.actor for t in plan.tasks] == [("a1", "paciente"), ("doc", "medico")]
    assert {t.owner for t in plan.tasks} == {("boss", "admin")}


def test_vertical_ignores_operations_the_account_map_did_not_assign() -> None:
    items = [ex("rel", account="boss")]

    plan = plan_vertical(items, ROLES, ORDER, assigned_to(), frozenset({"GET"}), frozenset())

    assert plan.tasks == ()
    assert plan.not_tested == ()


def test_vertical_ignores_a_request_sent_by_another_account_than_the_assigned_one() -> None:
    items = [ex("rel", account="a1")]

    plan = plan_vertical(
        items, ROLES, ORDER, assigned_to(("rel", "boss")), frozenset({"GET"}), frozenset()
    )

    assert plan.tasks == ()


def test_vertical_without_role_order_says_so_once() -> None:
    plan = plan_vertical(
        [ex("rel", account="boss")],
        ROLES,
        (),
        assigned_to(("rel", "boss")),
        frozenset({"GET"}),
        frozenset(),
    )

    assert plan.tasks == ()
    assert [n.reason for n in plan.not_tested] == ["no_role_order"]


def test_vertical_the_lowest_role_has_nobody_below() -> None:
    plan = plan_vertical(
        [ex("me", account="a1")],
        ROLES,
        ORDER,
        assigned_to(("me", "a1")),
        frozenset({"GET"}),
        frozenset(),
    )

    assert plan.not_tested[0].reason == "no_lower_role_account"


def test_vertical_a_role_missing_from_the_order_is_reported() -> None:
    roles = {**ROLES, "x": "estranho"}

    plan = plan_vertical(
        [ex("o", account="x")],
        roles,
        ORDER,
        assigned_to(("o", "x")),
        frozenset({"GET"}),
        frozenset(),
    )

    assert plan.not_tested[0].reason == "role_not_ranked"


def test_vertical_respects_the_method_list_and_public_operations() -> None:
    items = [
        ex("get", account="boss"),
        ex("post", method="POST", account="boss"),
        ex("pub", account="boss"),
    ]
    mapping = assigned_to(("get", "boss"), ("post", "boss"), ("pub", "boss"))

    plan = plan_vertical(items, ROLES, ORDER, mapping, frozenset({"GET"}), frozenset({"pub"}))

    assert {t.exchange.operation_id for t in plan.tasks} == {"get"}
    assert [n.operation_id for n in plan.not_tested] == ["pub"]


def test_vertical_never_plans_delete_even_if_somehow_listed() -> None:
    plan = plan_vertical(
        [ex("d", method="DELETE", account="boss")],
        ROLES,
        ORDER,
        assigned_to(("d", "boss")),
        frozenset({"GET", "POST"}),
        frozenset(),
    )

    assert plan.tasks == ()


# --- atribuição em massa -----------------------------------------------------------------------


def test_mass_assignment_pairs_the_update_with_a_read_of_the_same_path_and_account() -> None:
    body = json.dumps({"nome": "x"})
    items = [
        ex("ler", path="/api/me", target="/api/me"),
        ex("ler_outro", path="/api/me", target="/api/me", account="a2"),
        ex("atualizar", method="PUT", path="/api/me", target="/api/me", body=body),
    ]

    plan = plan_mass_assignment(items, frozenset())

    assert [
        (t.exchange.operation_id, t.read.operation_id if t.read else None) for t in plan.tasks
    ] == [("atualizar", "ler")]


def test_mass_assignment_without_a_read_uses_none() -> None:
    plan = plan_mass_assignment([ex("up", method="PATCH", path="/api/me", body="{}")], frozenset())

    assert plan.tasks[0].read is None


def test_mass_assignment_needs_a_json_object_body_and_never_touches_delete_or_post() -> None:
    items = [
        ex("sem_corpo", method="PUT"),
        ex("lista", method="PUT", body="[1]", path="/p2"),
        ex("quebrado", method="PUT", body="{oops", path="/p3"),
        ex("apaga", method="DELETE", body="{}"),
        ex("cria", method="POST", body="{}"),
        ex("pub", method="PUT", body="{}", path="/p4"),
    ]

    plan = plan_mass_assignment(items, frozenset({"pub"}))

    assert plan.tasks == ()
    assert {n.operation_id: n.reason for n in plan.not_tested} == {
        "sem_corpo": "no_json_body",
        "lista": "no_json_body",
        "quebrado": "no_json_body",
        "pub": "public_operation",
    }
