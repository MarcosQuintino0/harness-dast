"""`negative`: escrita só com a carta; PUT e PATCH aceitos são restaurados; POST conta criado."""

import json
from typing import Any

from harness_dast.application.negative import NegativeRequest
from harness_dast.application.negative_runner import MAX_CREATED_PER_OPERATION
from tests.fakes.negative_rig import (
    ADJUST,
    CREATE,
    SEED_PRODUCT,
    UPDATE,
    Catalog,
    NegativeRig,
)
from tests.fakes.probe_ports import reply


def bodies(rig: NegativeRig, method: str) -> list[dict[str, Any]]:
    return [json.loads(r.body or b"{}") for r in rig.sent(method)]


def original(exchange_body: str | None) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(exchange_body or "{}")
    return parsed


def restores(rig: NegativeRig) -> list[Any]:
    return [r for r in rig.target.requests if r.operation_id.startswith("negative:restore:")]


def test_an_accepted_put_is_followed_by_the_original_body_and_marked_restored() -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    result = rig.run(UPDATE)

    findings = [f for f in result.findings if f.method == "PUT"]
    assert findings
    assert all(f.restored is True for f in findings)
    assert all(f.created is False for f in findings)
    assert result.restored_resources == len(findings)
    sent = rig.sent("PUT")
    assert len(sent) == len(findings) * 2
    for index in range(1, len(sent), 2):
        assert json.loads(sent[index].body or b"{}") == original(UPDATE.body)
    assert len(restores(rig)) == len(findings)
    assert rig.catalog.product == {**SEED_PRODUCT, **original(UPDATE.body)}


def test_an_accepted_patch_is_restored_with_the_same_partial_body() -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    result = rig.run(ADJUST)

    assert result.findings
    assert all(f.restored is True for f in result.findings)
    assert json.loads(rig.sent("PATCH")[1].body or b"{}") == original(ADJUST.body)
    assert all("nome" not in body for body in bodies(rig, "PATCH"))


def test_a_rejected_put_is_not_restored_because_nothing_changed() -> None:
    rig = NegativeRig(Catalog(mode="validate"), allow_writes=True)

    result = rig.run(UPDATE)

    assert result.findings == ()
    assert restores(rig) == []
    assert result.restored_resources == 0


def test_a_put_that_answers_5xx_is_also_restored_because_the_state_is_uncertain() -> None:
    rig = NegativeRig(Catalog(mode="crash"), allow_writes=True)

    result = rig.run(UPDATE)

    assert {f.technique for f in result.findings} == {"input_server_error"}
    assert {f.proposed_severity for f in result.findings} == {"medium"}
    assert all(f.restored is True for f in result.findings)
    assert len(restores(rig)) == len(result.findings)


def test_a_restore_that_is_not_confirmed_warns_and_stops_the_operation() -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)
    probe = rig.seed(UPDATE)
    handler = rig.target._handler

    def refuse_restore(request: Any, jar: Any) -> Any:
        if request.operation_id.startswith("negative:restore:"):
            return reply(500, {"code": "ERRO_INTERNO"})
        return handler(request, jar)

    rig.target._handler = refuse_restore

    result = rig.negative().execute(NegativeRequest(product="agenda", run_id=probe.run_id))

    warnings = [n for n in result.not_tested if n.reason == "possible_unrestored_change"]
    assert len(warnings) == 1
    assert "adm" in warnings[0].message
    assert "atualizarProduto" in warnings[0].message
    assert [f.restored for f in result.findings] == [False]
    # O caso e a tentativa de restauração; nenhum outro caso parte com restauração pendente.
    assert len(rig.sent("PUT")) == 2
    pending = [n for n in result.not_tested if n.reason == "restore_pending"]
    assert len(pending) == 1
    assert "pendente" in pending[0].message
    assert result.restored_resources == 0


class WindowClosesAfterPut:
    """Trava que passa a valer assim que um PUT do negative chegou ao alvo."""

    def __init__(self, rig: NegativeRig) -> None:
        self._rig = rig

    def engaged(self) -> bool:
        return bool(self._rig.sent("PUT"))


def test_a_window_closing_right_after_the_put_is_reported_and_the_restore_does_not_leave() -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    result = rig.run(UPDATE, kill_switch=WindowClosesAfterPut(rig))

    assert result.status == "stopped_window"
    assert len(rig.sent("PUT")) == 1  # a restauração não fura a janela: nada sai depois
    warnings = [n for n in result.not_tested if n.reason == "possible_unrestored_change"]
    assert len(warnings) == 1
    assert warnings[0].operation_id == "atualizarProduto"
    assert [f.restored for f in result.findings] == [False]
    assert any(n.reason == "stopped" for n in result.not_tested)
    assert rig.artifacts.negative[result.run_id] == result


def test_an_accepted_post_counts_as_created_and_no_delete_is_ever_sent() -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    result = rig.run(CREATE)

    posts = rig.sent("POST")
    assert len(posts) == MAX_CREATED_PER_OPERATION
    assert result.created_resources == len(posts)
    assert all(f.created is True and f.restored is None for f in result.findings)
    assert rig.sent("DELETE") == []
    assert rig.catalog.deleted == 0
    assert restores(rig) == []


def test_a_post_operation_stops_after_two_accepted_creations() -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    result = rig.run(CREATE)

    left = [n for n in result.not_tested if n.reason == "created_limit"]
    assert len(left) == 1
    assert "hdast cleanup" in left[0].message


def test_a_rejected_post_creates_nothing_and_is_not_a_finding() -> None:
    rig = NegativeRig(Catalog(mode="validate"), allow_writes=True)
    probe = rig.seed(CREATE)
    before = len(rig.catalog.created)

    result = rig.negative().execute(NegativeRequest(product="agenda", run_id=probe.run_id))

    assert rig.sent("POST")
    assert result.findings == ()
    assert result.created_resources == 0
    assert len(rig.catalog.created) == before


def test_writes_stay_off_when_only_the_budget_knobs_are_set() -> None:
    rig = NegativeRig(Catalog(mode="lax"), max_requests=50, max_cases_per_operation=3)

    result = rig.run(CREATE, UPDATE, ADJUST)

    assert rig.sent() == []
    assert {n.reason for n in result.not_tested} == {"writes_not_authorized"}
