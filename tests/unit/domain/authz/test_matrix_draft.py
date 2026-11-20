"""Rascunho da tabela "quem pode o quê" (ADR 0041): hipótese, nunca `deny`, texto seguro."""

import yaml

from harness_dast.domain.authz.matrix import MAX_MATRIX_RULES, AccessRule
from harness_dast.domain.authz.matrix_draft import draft_items, render_draft
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.rig import operation

ROLES = {"med1": "medico", "adm1": "admin", "pac1": "paciente"}
OPS = [
    operation("login", "post", "/api/auth/login", secured=False),
    operation("getConsulta", "get", "/api/consultas/{id}"),
    operation("criarMedico", "post", "/api/medicos"),
    operation("lerCatalogo", "get", "/api/catalogo/{id}"),
]


def ex(op: str, account: str) -> ExchangeRecord:
    return ExchangeRecord(
        operation_id=op, method="GET", path="/x", target="/x", account=account, status=200
    )


def items(exchanges: list[ExchangeRecord] | None = None) -> tuple[object, ...]:
    return draft_items(
        OPS,
        exchanges or [],
        ROLES,
        ("paciente", "medico", "admin"),
        {"lerCatalogo"},
        {"/api/auth/login"},
    )


def test_one_item_per_operation_without_the_public_and_the_infrastructure_ones() -> None:
    found = draft_items(OPS, [], ROLES, (), {"lerCatalogo"}, {"/api/auth/login"})

    assert [i.operation for i in found] == ["getConsulta", "criarMedico"]
    assert [(i.method, i.path) for i in found] == [
        ("GET", "/api/consultas/{id}"),
        ("POST", "/api/medicos"),
    ]


def test_allow_comes_only_from_what_the_probe_saw_and_follows_the_role_order() -> None:
    found = draft_items(
        OPS,
        [ex("getConsulta", "adm1"), ex("getConsulta", "pac1"), ex("criarMedico", "adm1")],
        ROLES,
        ("paciente", "medico", "admin"),
        set(),
        set(),
    )

    by_op = {i.operation: i.allow for i in found}
    assert by_op["getConsulta"] == ("paciente", "admin")
    assert by_op["criarMedico"] == ("admin",)
    assert by_op["lerCatalogo"] == ()


def test_the_draft_never_fills_deny_and_marks_every_line_as_pending() -> None:
    text = render_draft(
        "demo", draft_items(OPS, [ex("getConsulta", "adm1")], ROLES, (), (), ()), with_run=True
    )

    document = yaml.safe_load(text)
    rows = document["authz"]["access_matrix"]
    assert rows
    assert all(row["deny"] == [] and row["review"] == "pendente" for row in rows)


def test_the_header_says_it_is_a_hypothesis_and_that_the_loader_ignores_it() -> None:
    text = render_draft("demo", (), with_run=False)

    head = text.split("authz:")[0]
    assert "HIPÓTESE" in head
    assert "NÃO vale nada" in head
    assert "não lê este arquivo" in head
    assert "nunca preenche deny" in head
    assert "allow está vazio (sem --run)" in head


def test_a_hostile_operation_name_cannot_break_out_of_its_yaml_string() -> None:
    hostile = 'x" # : [ {a: b} authz: evil: true '
    found = draft_items([operation(hostile, "get", "/a")], [], ROLES, (), (), ())

    document = yaml.safe_load(render_draft("demo", found, with_run=False))

    assert list(document) == ["authz"]
    assert document["authz"]["access_matrix"][0]["operation"] == hostile
    assert set(document["authz"]) == {"access_matrix"}


def test_a_huge_spec_is_cut_at_the_maximum_size_of_the_table() -> None:
    many = [operation(f"op{n}", "get", f"/a/{n}") for n in range(MAX_MATRIX_RULES + 30)]

    found = draft_items(many, [], ROLES, (), (), ())

    assert len(found) == MAX_MATRIX_RULES


def test_what_the_draft_suggests_after_trimming_is_a_valid_table() -> None:
    found = draft_items(
        OPS, [ex("getConsulta", "adm1")], ROLES, ("paciente", "medico", "admin"), (), ()
    )
    rows = yaml.safe_load(render_draft("demo", found, with_run=True))["authz"]["access_matrix"]

    rules = [
        AccessRule(operation=row["operation"], allow=row["allow"], deny=row["deny"]) for row in rows
    ]

    assert len(rules) == len(found)
