"""Seleção determinística, lacunas e vereditos conservadores da leitura de dono."""

import pytest

from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz_owner_plan import owner_pair, owner_verdict, plan_owner_reads
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.unit.domain.test_authz_owner_ids import ITEM, collection, exchange

ROLES = {"shared_a": "staff", "shared_b": "staff", "single": "alone", "a": "user", "b": "user"}


def test_par_quando_papel_compartilhado_e_conta_sem_par_sao_pulados() -> None:
    assert owner_pair(ROLES, ["staff"]) == ("a", "b")
    assert owner_pair(ROLES, []) == ("shared_a", "shared_b")
    assert owner_pair({"a": "user"}, []) is None
    assert owner_pair({"b": "user", "a": "user"}, []) == ("b", "a")


def test_plano_quando_colecao_propria_independe_da_conta_do_probe() -> None:
    shared = exchange(
        operation_id="read",
        method="GET",
        path=ITEM.path,
        target="/api/records/11",
        account="shared_a",
    )
    plan = plan_owner_reads([ITEM, collection()], [shared], ROLES, frozenset(), ["staff"])
    assert len(plan.tasks) == 1
    assert plan.tasks[0].owner == ("a", "user")
    assert plan.tasks[0].actor == ("b", "user")
    assert plan.tasks[0].collection == collection()


def test_nao_duplica_quando_probe_ja_alcancou_conta_com_par() -> None:
    reached = exchange(operation_id="read", method="GET", path=ITEM.path, target="/api/records/11")
    plan = plan_owner_reads([ITEM], [reached], ROLES, frozenset(), ["staff"])
    assert not plan.tasks
    assert not plan.not_tested


@pytest.mark.parametrize(
    ("operations", "exchanges", "roles", "public", "reason"),
    [
        ([ITEM], [], ROLES, {"read"}, "public_operation"),
        ([ITEM], [], {"a": "user"}, set(), "no_peer_account"),
        ([ITEM], [], ROLES, set(), "owner_collection_missing"),
        ([ITEM], [exchange(body="{}")], ROLES, set(), "ambiguous_identifier"),
        ([ITEM], [exchange(), exchange(account="b")], ROLES, set(), "ambiguous_identifier"),
        ([ITEM.model_copy(update={"parameters": ()})], [], ROLES, set(), "owner_read_unsupported"),
        (
            [ITEM, collection(), collection(operation_id="otherList")],
            [],
            ROLES,
            set(),
            "ambiguous_identifier",
        ),
    ],
)
def test_lacuna_quando_nao_ha_prova_para_montar_leitura(
    operations: list[Operation],
    exchanges: list[ExchangeRecord],
    roles: dict[str, str],
    public: set[str],
    reason: str,
) -> None:
    plan = plan_owner_reads(operations, exchanges, roles, frozenset(public), ["staff"])
    assert not plan.tasks
    assert plan.not_tested[0].reason == reason
    assert plan.not_tested[0].operation_id == "read"


def test_plano_quando_id_esta_em_criacao_da_conta() -> None:
    plan = plan_owner_reads([ITEM], [exchange()], ROLES, frozenset(), ["staff"])
    assert plan.tasks[0].identifiers == ("11",)
    assert plan.tasks[0].collection is None


@pytest.mark.parametrize(
    ("base", "replay", "same", "base_id", "replay_id", "wanted"),
    [
        (200, 200, True, True, True, "finding"),
        (201, 201, True, True, True, "finding"),
        (403, 200, True, True, True, "baseline_failed"),
        (200, 200, True, False, True, "baseline_failed"),
        (200, 401, False, True, False, "protected"),
        (200, 403, False, True, False, "protected"),
        (200, 404, False, True, False, "protected"),
        (200, 400, False, True, False, "inconclusive"),
        (200, 302, False, True, False, "inconclusive"),
        (200, 500, False, True, False, "inconclusive"),
        (200, None, False, True, False, "inconclusive"),
        (200, 200, False, True, True, "inconclusive"),
        (200, 200, True, True, False, "inconclusive"),
    ],
)
def test_veredito_quando_status_e_identidade_exigem_prova(
    base: int,
    replay: int | None,
    same: bool,
    base_id: bool,
    replay_id: bool,
    wanted: str,
) -> None:
    assert (
        owner_verdict(base, replay, same=same, baseline_identity=base_id, replay_identity=replay_id)
        == wanted
    )
