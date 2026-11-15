"""Plano do teste de autorização: o que repetir, com qual conta, e o que fica sem teste."""

from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz_identifiers import IdentifierRef
from harness_dast.domain.authz_plan import (
    MAX_PEERS,
    plan_excessive,
    plan_horizontal,
    plan_vertical,
)
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.rig import INT, operation, parameter

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
        "lista": "no_object_identifier",
    }


def query_list_op() -> Operation:
    return operation(
        "lista",
        "get",
        "/api/consultas",
        parameters=(parameter("pacienteId", INT, "query"), parameter("page", INT, "query")),
    )


def test_horizontal_a_get_with_an_identifier_in_the_query_enters_with_the_reference() -> None:
    item = ex("lista", path="/api/consultas", target="/api/consultas?pacienteId=2&page=1")

    plan = plan_horizontal([item], ROLES, frozenset(), [query_list_op()])

    assert [t.identifiers for t in plan.tasks] == [
        (IdentifierRef("query", "pacienteId", "name_only"),)
    ] * 2


def test_horizontal_a_path_identifier_keeps_the_query_references_empty() -> None:
    plan = plan_horizontal([ex("ver")], ROLES, frozenset())

    assert [t.identifiers for t in plan.tasks] == [()] * 2


def test_horizontal_a_collection_without_a_declared_identifier_is_no_object_identifier() -> None:
    item = ex("lista", path="/api/consultas", target="/api/consultas?pacienteId=2")

    without_spec = plan_horizontal([item], ROLES, frozenset())
    only_page = plan_horizontal(
        [ex("lista", path="/api/consultas", target="/api/consultas?page=1")],
        ROLES,
        frozenset(),
        [query_list_op()],
    )

    assert without_spec.tasks == ()
    assert only_page.tasks == ()
    assert [n.reason for n in without_spec.not_tested] == ["no_object_identifier"]
    assert [n.reason for n in only_page.not_tested] == ["no_object_identifier"]


def test_horizontal_a_query_identifier_with_an_odd_value_is_ambiguous_not_guessed() -> None:
    item = ex("lista", path="/api/consultas", target="/api/consultas?pacienteId=1,2")

    plan = plan_horizontal([item], ROLES, frozenset(), [query_list_op()])

    assert plan.tasks == ()
    assert [n.reason for n in plan.not_tested] == ["ambiguous_identifier"]
    assert "pacienteId" in plan.not_tested[0].message


def test_horizontal_a_declared_id_parameter_adds_a_read_candidate() -> None:
    op = operation("lista", "get", "/api/consultas", parameters=(parameter("cpf", INT, "query"),))
    item = ex("lista", path="/api/consultas", target="/api/consultas?cpf=123")

    plan = plan_horizontal([item], ROLES, frozenset(), [op], ("cpf",))

    assert len(plan.tasks) == 2


def test_horizontal_a_query_identifier_respects_public_operations_and_peers() -> None:
    item = ex("lista", path="/api/consultas", target="/api/consultas?pacienteId=2")
    lone = ex("lista", path="/api/consultas", target="/api/consultas?pacienteId=2", account="boss")

    public = plan_horizontal([item], ROLES, frozenset({"lista"}), [query_list_op()])
    alone = plan_horizontal([lone], ROLES, frozenset(), [query_list_op()])

    assert [n.reason for n in public.not_tested] == ["public_operation"]
    assert [n.reason for n in alone.not_tested] == ["no_peer_account"]


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


def test_shared_role_is_skipped_while_another_role_is_compared() -> None:
    roles = {**ROLES, "doc2": "medico"}
    plan = plan_horizontal(
        [ex("paciente"), ex("medico", account="doc")], roles, frozenset(), shared_roles=("medico",)
    )
    assert {task.exchange.operation_id for task in plan.tasks} == {"paciente"}
    assert [(note.operation_id, note.reason) for note in plan.not_tested] == [
        ("medico", "shared_role")
    ]


def test_shared_role_preserves_public_and_missing_identifier_reasons() -> None:
    items = [ex("publica"), ex("colecao", path="/api/x", target="/api/x")]
    plan = plan_horizontal(items, ROLES, frozenset({"publica"}), shared_roles=("paciente",))
    assert plan.tasks == ()
    assert {n.operation_id: n.reason for n in plan.not_tested} == {
        "publica": "public_operation",
        "colecao": "no_object_identifier",
    }
