"""Planejamento do `probe`: ordem, pulos por escopo, negação e DELETE."""

from collections.abc import Iterable
from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_plan import (
    PlannedOperation,
    looks_destructive,
    plan_probe,
    probe_url_for,
)
from tests.fakes.rig import agenda_flows, agenda_profile, agenda_spec, operation

BASE = "https://api.hml.acme-teste.net.br"


def plan(**changes: Any) -> tuple[PlannedOperation, ...]:
    profile = agenda_profile()
    return plan_probe(
        agenda_spec(), agenda_flows(), profile.guard(), profile.environment.base_url, **changes
    )


def decisions(items: Iterable[PlannedOperation]) -> dict[str, str]:
    return {i.operation_id: i.decision for i in items}


def test_producers_come_before_consumers_and_deletes_come_last() -> None:
    names = [i.operation_id for i in plan(include_delete=True)]

    assert names.index("criar") < names.index("buscar")
    assert names.index("criar") < names.index("atualizar")
    assert names[-1] == "remover"


def test_without_flows_the_openapi_order_is_kept_except_deletes() -> None:
    profile = agenda_profile()

    items = plan_probe(agenda_spec(), None, profile.guard(), BASE)

    assert [i.operation_id for i in items] == [
        "login",
        "listar",
        "criar",
        "buscar",
        "atualizar",
        "admin",
        "externo",
        "remover",
    ]


def test_scope_deny_and_destructive_decisions_are_explained() -> None:
    items = {i.operation_id: i for i in plan()}

    assert items["admin"].decision == "skipped_denied"
    assert items["externo"].decision == "skipped_scope"
    assert items["remover"].decision == "skipped_destructive"
    assert items["buscar"].decision == "send"
    for name in ("admin", "externo", "remover"):
        assert items[name].reason


def test_delete_is_sent_only_with_the_flag_and_when_fed_by_a_flow() -> None:
    assert decisions(plan(include_delete=True))["remover"] == "send"
    assert decisions(plan(include_delete=False))["remover"] == "skipped_destructive"

    profile = agenda_profile()
    no_flow = plan_probe(agenda_spec(), None, profile.guard(), BASE, include_delete=True)
    assert decisions(no_flow)["remover"] == "skipped_destructive"


def test_a_delete_outside_the_allowed_methods_is_a_scope_skip_not_a_destructive_one() -> None:
    profile = agenda_profile(
        scope={
            **agenda_profile().scope.model_dump(mode="json"),
            "allow": [
                {
                    "host": "api.hml.acme-teste.net.br",
                    "paths": ["/api/**"],
                    "methods": ["GET", "POST", "PUT"],
                }
            ],
        }
    )

    items = plan_probe(agenda_spec(), agenda_flows(), profile.guard(), BASE, include_delete=True)

    assert decisions(items)["remover"] == "skipped_scope"


def test_dependency_information_is_exposed() -> None:
    items = {i.operation_id: i for i in plan()}

    assert items["buscar"].depends_on == ("criar",)
    assert items["criar"].is_producer is True
    assert items["listar"].depends_on == ()


def test_only_keeps_the_selection_and_its_producers() -> None:
    names = [i.operation_id for i in plan(only=("atualizar", "listar"))]

    assert names == ["listar", "criar", "atualizar"]


def test_only_rejects_unknown_operations_with_a_hint() -> None:
    with pytest.raises(ConfigError) as info:
        plan(only=("nada",))

    assert info.value.hint


def test_scope_check_url_replaces_placeholders_with_a_neutral_segment() -> None:
    op = agenda_spec().get_operation("buscar")

    assert probe_url_for(op, BASE + "/") == f"{BASE}/api/pacientes/x"


@pytest.mark.parametrize(
    ("operation_id", "path", "expected"),
    [
        ("api.main.populate_db", "/createdb", True),
        ("x", "/admin/reset", True),
        ("limpar", "/api/purge", True),
        ("listar", "/api/pacientes", False),
        ("buscar", "/api/pacientes/{id}", False),
    ],
)
def test_destructive_looking_names_are_flagged(
    operation_id: str, path: str, expected: bool
) -> None:
    assert looks_destructive(operation(operation_id, "get", path)) is expected
