"""`authz`: `horizontal_write`, a conta B tenta alterar o recurso da conta A (ADR 0042)."""

import json
from typing import Any

import pytest

from harness_dast.domain.authz_result import AuthzNotTested, AuthzResult
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.authz_rig import AuthzRig
from tests.fakes.authz_write_rig import (
    ORIGINAL_TITLE,
    PATCH_NOTE,
    PUT_NOTE,
    READ_NOTE,
    Notes,
    authz_sent,
    exchange,
    notes_rig,
    run_checks,
    seed,
)

MARKER = f"{ORIGINAL_TITLE}-hdast"


def run_write(rig: AuthzRig, *exchanges: ExchangeRecord) -> AuthzResult:
    return run_checks(rig, exchanges or (READ_NOTE, PUT_NOTE), "horizontal_write")


def reasons(result: AuthzResult) -> dict[str, str]:
    return {n.reason: n.message for n in result.not_tested}


def notes_with(result: AuthzResult, reason: str) -> list[AuthzNotTested]:
    return [n for n in result.not_tested if n.reason == reason]


def title_of(rig: AuthzRig) -> str:
    assert isinstance(rig.clinic, Notes)
    return str(rig.clinic.notes[1]["titulo"])


def test_a_vulnerable_server_gives_a_high_finding_and_the_owner_value_is_restored() -> None:
    rig = notes_rig(Notes(write="vulnerable"))

    result = run_write(rig)

    (found,) = result.findings
    assert found.technique == "authz_horizontal_write"
    assert (found.proposed_severity, found.cwe) == ("high", 639)
    assert found.owasp_api_2023.startswith("API1:2023")
    assert (found.actor_account, found.owner_account) == ("pac_b", "pac_a")
    assert (found.method, found.fields, found.observed_status) == ("PUT", ("titulo",), 200)
    assert "restaurado" in found.evidence
    assert title_of(rig) == ORIGINAL_TITLE
    assert notes_with(result, "possible_unrestored_change") == []


def test_the_requests_are_read_before_write_by_b_read_after_and_restore_by_the_owner() -> None:
    rig = notes_rig(Notes(write="vulnerable"))

    run_write(rig)

    sent = authz_sent(rig)
    assert [(r.method, r.account, r.operation_id) for r in sent] == [
        ("GET", "pac_a", "authz:lerNota"),
        ("PUT", "pac_b", "authz:write:salvarNota"),
        ("GET", "pac_a", "authz:lerNota"),
        ("PUT", "pac_a", "authz:salvarNota"),
        ("GET", "pac_a", "authz:lerNota"),
    ]


def test_only_one_field_of_the_proven_body_changes_in_the_write_of_the_other_account() -> None:
    rig = notes_rig(Notes(write="vulnerable"))

    run_write(rig)

    written = json.loads(authz_sent(rig, "PUT")[0].body or b"{}")
    proven = json.loads(PUT_NOTE.body or "{}")
    assert [name for name in proven if written[name] != proven[name]] == ["titulo"]
    assert written["titulo"] == MARKER


def test_a_patch_is_tested_too() -> None:
    rig = notes_rig(Notes(write="vulnerable"))

    result = run_write(rig, READ_NOTE, PATCH_NOTE)

    assert [f.method for f in result.findings] == ["PATCH"]
    assert authz_sent(rig, "PATCH")[0].account == "pac_b"


@pytest.mark.parametrize("status", [401, 403, 404])
def test_denial_statuses_are_not_a_finding_and_nothing_else_is_sent(status: int) -> None:
    rig = notes_rig(Notes(write="deny", deny_status=status))

    result = run_write(rig)

    assert result.findings == ()
    sent = [(r.method, r.account) for r in authz_sent(rig)]
    # o 401 pode repetir a escrita de B depois de um novo login; nada é lido nem restaurado
    assert sent[0] == ("GET", "pac_a")
    assert set(sent[1:]) == {("PUT", "pac_b")}
    (summary,) = [c for c in result.checks if c.check == "horizontal_write"]
    assert (summary.tested, summary.findings, summary.status) == (1, 0, "completed")
    assert title_of(rig) == ORIGINAL_TITLE


def test_a_2xx_without_visible_effect_is_reported_and_never_green() -> None:
    rig = notes_rig(Notes(write="ignore"))

    result = run_write(rig)

    assert result.findings == ()
    (item,) = notes_with(result, "accepted_without_visible_effect")
    assert "NÃO é seguro" in item.message
    summary = next(c for c in result.checks if c.check == "horizontal_write")
    assert summary.tested == 0
    assert summary.status == "skipped"


@pytest.mark.parametrize("status", [400, 409, 422, 500])
def test_rejections_and_server_errors_do_not_conclude(status: int) -> None:
    rig = notes_rig(Notes(write="vulnerable", write_status=status))

    result = run_write(rig)

    assert result.findings == ()
    assert len(notes_with(result, "inconclusive")) == 1
    assert [r.method for r in authz_sent(rig)] == ["GET", "PUT"]


def test_without_allow_writes_nothing_is_sent_and_the_check_says_why() -> None:
    rig = notes_rig(Notes(write="vulnerable"), allow_writes=False)

    result = run_write(rig)

    assert authz_sent(rig) == []
    assert [n.reason for n in notes_with(result, "writes_not_authorized")] == [
        "writes_not_authorized"
    ]
    summary = next(c for c in result.checks if c.check == "horizontal_write")
    assert summary.status == "skipped"
    assert "escrita não autorizada" in (summary.message or "")


def test_a_delete_and_a_post_are_never_repeated_by_the_other_account() -> None:
    rig = notes_rig(Notes(write="vulnerable"))
    delete = exchange("apagarNota", "DELETE", "/api/notas/{id}", "/api/notas/1")
    post = exchange("criarNota", "POST", "/api/notas/{id}", "/api/notas/1", body={"titulo": "x"})

    run_write(rig, READ_NOTE, PUT_NOTE, delete, post)

    assert {r.method for r in authz_sent(rig)} <= {"GET", "PUT"}


def test_a_method_outside_the_scope_is_refused_by_the_guard_and_nothing_is_written() -> None:
    rig = notes_rig(Notes(write="vulnerable"), methods=["GET", "POST"])

    result = run_write(rig)

    assert authz_sent(rig, "PUT") == []
    assert result.findings == ()
    assert len(notes_with(result, "scope_denied")) == 1


def test_a_denied_path_is_refused_by_the_guard_and_nothing_reaches_the_target() -> None:
    rig = notes_rig(Notes(write="vulnerable"))
    admin_read = exchange("lerNota", "GET", "/api/admin/notas/{id}", "/api/admin/notas/1")
    admin_put = exchange(
        "salvarNota",
        "PUT",
        "/api/admin/notas/{id}",
        "/api/admin/notas/1",
        body={"titulo": "Original", "ordem": 3},
    )

    result = run_write(rig, admin_read, admin_put)

    assert [r for r in rig.target.requests if "/api/admin/" in r.url] == []
    assert result.findings == ()
    assert len(notes_with(result, "scope_denied")) == 1


class WindowClosesAfterWrite:
    """Trava que passa a valer quando a escrita da outra conta chegou ao alvo."""

    def __init__(self, rig: AuthzRig) -> None:
        self._rig = rig

    def engaged(self) -> bool:
        return any(r.operation_id.startswith("authz:write:") for r in self._rig.target.requests)


def test_a_window_closing_after_the_write_is_reported_as_possible_unrestored_change() -> None:
    rig = notes_rig(Notes(write="vulnerable"))
    probe = seed(rig, READ_NOTE, PUT_NOTE)
    from harness_dast.application.authz import Authz, AuthzRequest

    stage = Authz(
        profiles=rig.profiles,
        specs=rig._specs(),
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        store=rig.store,
        artifacts=rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
        kill_switch=WindowClosesAfterWrite(rig),
    )

    result = stage.execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("horizontal_write",))
    )

    assert result.status == "stopped_window"
    assert [r.account for r in authz_sent(rig, "PUT")] == [
        "pac_b"
    ]  # a janela fechada barra a volta
    (item,) = notes_with(result, "possible_unrestored_change")
    assert item.operation_id == "salvarNota"
    assert "pac_a" in item.message
    assert "pac_b" in item.message


def test_an_interrupted_read_after_the_write_still_restores_through_the_owner() -> None:
    rig = notes_rig(Notes(write="vulnerable"))
    original = rig.target._handler

    def broken(request: Any, jar: Any) -> Any:
        wrote = any(r.operation_id.startswith("authz:write:") for r in rig.target.requests)
        if wrote and request.method == "GET" and request.operation_id.startswith("authz:"):
            return ExternalToolError("O proxy do ZAP não respondeu.")
        return original(request, jar)

    rig.target._handler = broken

    result = run_write(rig)

    assert result.status == "stopped_zap"
    assert title_of(rig) == ORIGINAL_TITLE  # a dona reenviou o valor anterior
    assert [r.account for r in authz_sent(rig, "PUT")] == ["pac_b", "pac_a"]


def test_a_restore_that_does_not_take_is_reported_in_the_finding_and_in_not_tested() -> None:
    rig = notes_rig(Notes(write="vulnerable", owner_write_ignored=True))

    result = run_write(rig)

    (found,) = result.findings
    assert "NÃO pôde ser restaurado" in found.evidence
    assert len(notes_with(result, "possible_unrestored_change")) == 1
    assert title_of(rig) == MARKER


def test_marker_and_field_values_never_reach_the_artifacts() -> None:
    rig = notes_rig(Notes(write="vulnerable"))

    result = run_write(rig)

    everything = result.model_dump_json() + rig.artifacts.serialized()
    assert MARKER not in everything
    assert ORIGINAL_TITLE not in everything


def test_a_body_without_a_detectable_field_is_not_written() -> None:
    rig = notes_rig(Notes(write="vulnerable"))
    only_role = exchange(
        "salvarNota", "PUT", "/api/notas/{id}", "/api/notas/1", body={"role": "visitante"}
    )

    result = run_write(rig, READ_NOTE, only_role)

    assert len(notes_with(result, "no_detectable_field")) == 1
    assert authz_sent(rig, "PUT") == []


def test_an_operation_without_the_reading_is_not_written_blindly() -> None:
    rig = notes_rig(Notes(write="vulnerable"))

    result = run_write(rig, PUT_NOTE)

    assert len(notes_with(result, "no_read_to_confirm")) == 1
    assert authz_sent(rig) == []


def test_an_operation_that_acts_on_the_caller_has_no_object_identifier() -> None:
    rig = notes_rig(Notes(write="vulnerable"))
    me = exchange("atualizarPerfil", "PUT", "/api/me", "/api/me", body={"nome": "x"})

    result = run_write(rig, me)

    assert len(notes_with(result, "no_object_identifier")) == 1
    assert authz_sent(rig) == []


def test_a_public_operation_and_a_missing_peer_are_reported() -> None:
    public = notes_rig(Notes(write="vulnerable"), public_operations=["salvarNota"])

    assert len(notes_with(run_write(public), "public_operation")) == 1
    assert authz_sent(public) == []

    alone = notes_rig(Notes(write="vulnerable"))
    only_admin = exchange(
        "salvarNota", "PUT", "/api/notas/{id}", "/api/notas/1", account="adm", body={"titulo": "x"}
    )
    admin_read = exchange("lerNota", "GET", "/api/notas/{id}", "/api/notas/1", account="adm")
    result = run_write(alone, admin_read, only_admin)
    assert len(notes_with(result, "no_peer_account")) == 1


def test_dry_run_lists_the_candidates_and_sends_nothing() -> None:
    rig = notes_rig(Notes(write="vulnerable"))

    result = run_checks(rig, (READ_NOTE, PUT_NOTE), "horizontal_write", dry_run=True)

    summary = next(c for c in result.checks if c.check == "horizontal_write")
    assert summary.candidates == 1
    assert authz_sent(rig) == []
    assert result.findings == ()


def test_a_failing_baseline_read_is_not_tested() -> None:
    rig = notes_rig(Notes(write="vulnerable"))
    missing = exchange("lerNota", "GET", "/api/notas/{id}", "/api/notas/99")
    put_missing = exchange(
        "salvarNota", "PUT", "/api/notas/{id}", "/api/notas/99", body={"titulo": "x"}
    )

    result = run_write(rig, missing, put_missing)

    assert len(notes_with(result, "baseline_failed")) == 1
    assert authz_sent(rig, "PUT") == []
