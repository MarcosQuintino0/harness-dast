"""Receitas só conectam leituras provadas aos candidatos já autorizados."""

from harness_dast.domain.authz.candidates import Candidate
from harness_dast.domain.authz.effect_plan import apply_effect_recipes
from harness_dast.domain.authz.plan import Planned
from harness_dast.domain.authz.plan_mass import MassTask
from harness_dast.domain.knowledge import KnowledgeEffect
from tests.fakes.authz.write_rig import exchange
from tests.fakes.rig import INT, operation, parameter


def test_recipe_maps_proven_reader_only_to_existing_matching_candidate() -> None:
    write = exchange("write", "POST", "/submissions", "/submissions", account="adm", body={"x": 1})
    read = exchange("read", "GET", "/objects/{id}", "/objects/8", account="adm")
    candidates = (
        Candidate("balance", "declared", "balance", declared_value=2),
        Candidate("price", "declared", "price", declared_value=3),
    )
    task = MassTask(write, None, candidates, created=True)
    operations = {
        "write": operation("write", "post", "/submissions"),
        "read": operation(
            "read",
            "get",
            "/objects/{id}",
            parameters=(parameter("id"),),
            produces={"id": INT, "balance": INT, "price": INT},
        ),
    }
    recipe = KnowledgeEffect(
        write_operation="write",
        read_operation="read",
        account="adm",
        fields=("balance",),
        proof="readback_verified",
    )
    result = apply_effect_recipes(
        Planned((task,), ()), (write, read), operations, (recipe,), frozenset(), frozenset()
    )
    assert len(result.tasks) == 1
    assert result.tasks[0].candidate_readers == (("balance", read),)
    assert tuple(candidate.name for item in result.tasks for candidate in item.candidates) == (
        "balance",
        "price",
    )


def test_recipe_cannot_create_task_or_use_unproven_wrong_account_reader() -> None:
    write = exchange("write", "POST", "/submissions", "/submissions", account="adm", body={"x": 1})
    read = exchange("read", "GET", "/objects/{id}", "/objects/8", account="other")
    task = MassTask(
        write, None, (Candidate("balance", "declared", "balance", declared_value=2),), created=True
    )
    operations = {
        "write": operation("write", "post", "/submissions"),
        "read": operation(
            "read",
            "get",
            "/objects/{id}",
            parameters=(parameter("id"),),
            produces={"id": INT, "balance": INT},
        ),
    }
    recipe = KnowledgeEffect(
        write_operation="write",
        read_operation="read",
        account="adm",
        fields=("balance",),
        proof="readback_verified",
    )
    assert (
        apply_effect_recipes(
            Planned((), ()), (write, read), operations, (recipe,), frozenset(), frozenset()
        ).tasks
        == ()
    )
    assert apply_effect_recipes(
        Planned((task,), ()), (write, read), operations, (recipe,), frozenset(), frozenset()
    ).tasks == (task,)
