# ruff: noqa: S608
"""QA independente do caso de uso `Cleanup` (`application/cleanup.py`).

Escrito a partir do docstring do módulo e das portas: tudo que pode ser recusado é recusado
ANTES de conectar; `--dry-run` sempre desfaz; sem confirmação da pessoa nada é gravado; o token
é de uso único e amarrado a produto, execução e script; o teto de linhas vale sempre; nenhum
valor de ligação nem credencial aparece no que é gravado.
"""

from datetime import timedelta
from typing import Any

import pytest

from harness_dast.application.cleanup import CleanupRequest
from harness_dast.domain.errors import CleanupError, ConfigError, ScopeViolation
from tests.fakes.cleanup_rig import RUN_ID, SCRIPT, SECRETS, CleanupRig, cleanup_profile

OTHER_RUN = "2026-11-10T10-00-00Z-demo-aaaa"


def committed_rows(rig: CleanupRig) -> dict[str, int]:
    return dict(rig.database.committed)


# --------------------------------------------------------------------------- dry-run


def test_execute_never_commits_when_run_is_dry_run() -> None:
    rig = CleanupRig()

    report = rig.run(dry_run=True)

    assert report.status == "dry_run"
    assert report.committed is False
    assert report.rolled_back is True
    assert rig.database.commits == 0
    assert committed_rows(rig) == {"PEDIDO": 10, "ITEM": 20}


def test_execute_counts_rows_without_applying_when_run_is_dry_run() -> None:
    rig = CleanupRig(matches={1: 3, 2: 2})

    report = rig.run(dry_run=True)

    assert report.total_rows == 5
    assert [item.rows for item in report.statements] == [3, 2]


def test_execute_keeps_token_out_of_every_serialization_when_dry_run_issues_it() -> None:
    rig = CleanupRig()

    report = rig.run(dry_run=True)

    token = report.confirmation_token
    assert token is not None
    assert token not in report.model_dump_json()
    assert token not in str(report.model_dump(mode="json"))
    assert token not in rig.runs.serialized()
    assert token not in repr(report)


def test_execute_rejects_dry_run_combined_with_confirm_token() -> None:
    rig = CleanupRig()
    rig.run(dry_run=True)

    with pytest.raises(ConfigError):
        rig.run(dry_run=True, confirm="tok-1")

    assert rig.database.commits == 0


# --------------------------------------------------------------- sem confirmação


def test_execute_refuses_before_connecting_when_there_is_no_terminal_and_no_token() -> None:
    rig = CleanupRig()

    with pytest.raises(ConfigError):
        rig.run(dry_run=False, confirm=None, interactive=False)

    assert rig.database.opened == []
    assert rig.database.commits == 0


def test_execute_rolls_back_when_the_person_declines_at_the_terminal() -> None:
    rig = CleanupRig(prompt_answer=False)

    report = rig.run(interactive=True)

    assert report.status == "declined"
    assert report.committed is False
    assert rig.database.commits == 0
    assert committed_rows(rig) == {"PEDIDO": 10, "ITEM": 20}


def test_execute_commits_only_after_the_person_confirms_at_the_terminal() -> None:
    rig = CleanupRig(prompt_answer=True)

    report = rig.run(interactive=True)

    assert report.status == "committed"
    assert report.confirmation_method == "interactive"
    assert rig.database.commits == 1
    assert len(rig.prompt.plans) == 1
    assert rig.prompt.plans[0].total_rows == 5


# ------------------------------------------------------------------------- token


def test_execute_commits_when_token_comes_from_a_previous_dry_run() -> None:
    rig = CleanupRig()
    token = rig.run(dry_run=True).confirmation_token
    assert token is not None

    report = rig.run(confirm=token)

    assert report.status == "committed"
    assert report.confirmation_method == "token"
    assert rig.database.commits == 1


def test_execute_refuses_second_use_when_token_was_already_spent() -> None:
    rig = CleanupRig()
    token = rig.run(dry_run=True).confirmation_token
    assert token is not None
    rig.run(confirm=token)

    with pytest.raises(ConfigError):
        rig.run(confirm=token)

    assert rig.database.commits == 1


def test_execute_refuses_when_token_is_wrong() -> None:
    rig = CleanupRig()
    rig.run(dry_run=True)

    with pytest.raises(ConfigError):
        rig.run(confirm="hdc-chute")

    assert rig.database.commits == 0


def test_execute_refuses_when_token_was_never_issued() -> None:
    rig = CleanupRig()

    with pytest.raises(ConfigError):
        rig.run(confirm="hdc-inventado")

    assert rig.database.opened == []


def test_execute_refuses_when_token_has_expired() -> None:
    rig = CleanupRig()
    token = rig.run(dry_run=True).confirmation_token
    assert token is not None
    rig.clock.advance(timedelta(minutes=11).total_seconds())

    with pytest.raises(ConfigError):
        rig.run(confirm=token)

    assert rig.database.commits == 0


def test_execute_refuses_when_script_changed_after_the_dry_run() -> None:
    rig = CleanupRig()
    token = rig.run(dry_run=True).confirmation_token
    assert token is not None
    rig.scripts.content = (SCRIPT + "DELETE FROM ITEM WHERE RUN_ID = :run_id;\n").encode()

    with pytest.raises(ConfigError):
        rig.run(confirm=token)

    assert rig.database.commits == 0


def test_execute_refuses_when_token_is_replayed_for_another_run() -> None:
    rig = CleanupRig()
    token = rig.run(dry_run=True).confirmation_token
    assert token is not None
    assert rig.runs.manifest is not None
    rig.runs.manifest = rig.runs.manifest.model_copy(update={"run_id": OTHER_RUN})

    with pytest.raises(ConfigError):
        rig.run(confirm=token, run_id=OTHER_RUN)

    assert rig.database.commits == 0


def test_execute_refuses_commit_when_rows_grew_after_the_dry_run() -> None:
    rig = CleanupRig(matches={1: 3, 2: 2})
    token = rig.run(dry_run=True).confirmation_token
    assert token is not None
    rig.database.matches = {1: 40, 2: 2}

    with pytest.raises(CleanupError):
        rig.run(confirm=token)

    assert rig.database.commits == 0
    assert rig.database.rollbacks >= 1


def test_execute_commits_when_rows_shrank_after_the_dry_run() -> None:
    rig = CleanupRig(matches={1: 3, 2: 2})
    token = rig.run(dry_run=True).confirmation_token
    assert token is not None
    rig.database.matches = {1: 1, 2: 0}

    report = rig.run(confirm=token)

    assert report.status == "committed"
    assert report.total_rows == 1


# ------------------------------------------------------------------------- teto


def test_execute_rolls_back_and_raises_when_total_rows_exceed_the_profile_ceiling() -> None:
    rig = CleanupRig(matches={1: 60, 2: 41})

    with pytest.raises(CleanupError):
        rig.run(interactive=True)

    assert rig.database.commits == 0
    assert rig.prompt.plans == []
    assert rig.runs.records[-1].status == "failed"
    assert rig.runs.records[-1].committed is False


def test_execute_applies_the_ceiling_to_dry_run_too() -> None:
    rig = CleanupRig(matches={1: 101})

    with pytest.raises(CleanupError):
        rig.run(dry_run=True)

    assert rig.runs.confirmation is None


def test_execute_accepts_total_equal_to_the_ceiling() -> None:
    rig = CleanupRig(matches={1: 60, 2: 40})

    report = rig.run(interactive=True)

    assert report.status == "committed"


# --------------------------------------------------------- recusas antes de conectar


def test_execute_refuses_before_connecting_when_run_is_still_in_progress() -> None:
    rig = CleanupRig(finished_at=None)
    rig.clock.advance(-(90 * 60))  # 10:30, dentro dos 60 min do prazo da execução

    with pytest.raises(ConfigError):
        rig.run(dry_run=True)

    assert rig.database.opened == []


def test_execute_refuses_before_connecting_when_run_does_not_exist() -> None:
    rig = CleanupRig()

    with pytest.raises(ConfigError):
        rig.run(dry_run=True, run_id=OTHER_RUN)

    assert rig.database.opened == []


@pytest.mark.parametrize("bad_run_id", ["../../etc", "", "x", RUN_ID + "/..", "run id"])
def test_execute_refuses_when_run_id_is_not_a_valid_identifier(bad_run_id: str) -> None:
    rig = CleanupRig()

    with pytest.raises(ConfigError):
        rig.run(dry_run=True, run_id=bad_run_id)

    assert rig.database.opened == []


def test_execute_refuses_before_connecting_when_authorization_has_expired() -> None:
    rig = CleanupRig(profile=cleanup_profile(valid_until="2026-11-09"))

    with pytest.raises(ScopeViolation):
        rig.run(dry_run=True)

    assert rig.database.opened == []


def test_execute_does_not_require_an_open_window_when_the_authorization_is_valid() -> None:
    rig = CleanupRig(profile=cleanup_profile(window="seg 03:00-03:30 UTC"))

    report = rig.run(dry_run=True)

    assert report.status == "dry_run"


@pytest.mark.parametrize("missing", ["user", "password", "allowed_tables", "max_rows"])
def test_execute_refuses_before_connecting_when_profile_lacks_a_required_cleanup_field(
    missing: str,
) -> None:
    empty: dict[str, Any] = {
        "user": None,
        "password": None,
        "allowed_tables": [],
        "max_rows": None,
    }
    rig = CleanupRig(profile=cleanup_profile(**{missing: empty[missing]}))

    with pytest.raises(ConfigError):
        rig.run(dry_run=True)

    assert rig.database.opened == []


def test_execute_refuses_before_connecting_when_script_deletes_without_where() -> None:
    rig = CleanupRig(script="DELETE FROM PEDIDO;")

    with pytest.raises(ConfigError):
        rig.run(dry_run=True)

    assert rig.database.opened == []


def test_execute_refuses_before_connecting_when_script_touches_a_table_not_allowed() -> None:
    rig = CleanupRig(script="DELETE FROM USUARIO WHERE RUN_ID = :run_id;")

    with pytest.raises(ConfigError):
        rig.run(dry_run=True)

    assert rig.database.opened == []


def test_execute_refuses_before_connecting_when_a_secret_is_not_defined() -> None:
    secrets = dict(SECRETS)
    del secrets["ACME_ORACLE_PASSWORD"]
    rig = CleanupRig(secrets=secrets)

    with pytest.raises(ConfigError):
        rig.run(dry_run=True)

    assert rig.database.opened == []


# ------------------------------------------------------------------------- falhas


def test_execute_rolls_back_everything_when_second_statement_fails() -> None:
    rig = CleanupRig()
    rig.database.fail_at = 2

    with pytest.raises(CleanupError):
        rig.run(interactive=True)

    assert rig.database.commits == 0
    assert committed_rows(rig) == {"PEDIDO": 10, "ITEM": 20}
    assert rig.runs.records[-1].failed_statement == 2
    assert rig.database.closed == 1


def test_execute_never_reports_committed_when_the_commit_itself_fails() -> None:
    rig = CleanupRig()
    rig.database.fail_commit = True

    with pytest.raises(CleanupError):
        rig.run(interactive=True)

    assert rig.runs.records[-1].committed is False
    assert rig.runs.records[-1].status == "failed"


def test_execute_closes_the_connection_when_the_database_refuses_the_connection() -> None:
    rig = CleanupRig()
    rig.database.fail_open = True

    with pytest.raises(CleanupError):
        rig.run(dry_run=True)

    assert rig.database.commits == 0


def test_execute_audits_start_and_finish_for_every_attempt_that_reaches_the_database() -> None:
    rig = CleanupRig()
    rig.database.fail_at = 1

    with pytest.raises(CleanupError):
        rig.run(dry_run=True)

    events = [line.event for line in rig.runs.audit]
    assert events == ["started", "finished"]


def test_execute_audits_a_finish_line_when_the_driver_raises_an_unexpected_exception() -> None:
    # Defeito: só `CleanupError` é tratado em `execute`. Qualquer outra exceção (bug do driver,
    # erro de E/S ao gravar a confirmação) sai sem linha `finished`, sem `cleanup.json` e sem
    # ROLLBACK explícito: a trilha mostra uma tentativa que "começou e nunca terminou".
    rig = CleanupRig()
    original = rig.executor.open

    def broken_open(connection: object) -> object:
        session = original(connection)  # type: ignore[arg-type]

        def explode(*_: object, **__: object) -> int:
            raise RuntimeError("driver quebrou")

        session.execute = explode  # type: ignore[method-assign]
        return session

    rig.executor.open = broken_open  # type: ignore[method-assign, assignment]

    with pytest.raises(RuntimeError):
        rig.run(dry_run=True)

    events = [line.event for line in rig.runs.audit]
    assert events == ["started", "finished"]


# --------------------------------------------------------------------- vazamentos


def test_execute_never_writes_credentials_or_bind_values_when_run_is_committed() -> None:
    rig = CleanupRig()
    token = rig.run(dry_run=True).confirmation_token
    assert token is not None
    rig.run(confirm=token)

    written = rig.runs.serialized()

    for secret in SECRETS.values():
        assert secret not in written
    assert "tok-1" not in written


def test_execute_registers_secrets_in_the_vault_so_logs_can_mask_them() -> None:
    rig = CleanupRig()

    rig.run(dry_run=True)

    masked = rig.vault.mask("x " + SECRETS["ACME_ORACLE_PASSWORD"] + " y")
    assert SECRETS["ACME_ORACLE_PASSWORD"] not in masked


def test_execute_passes_only_the_binds_each_statement_uses() -> None:
    rig = CleanupRig()

    rig.run(dry_run=True)

    first, second = rig.database.executed
    assert set(first[1]) == {"run_id"}
    assert set(second[1]) == {"run_start", "account_1"}


def test_execute_request_is_a_plain_value_object() -> None:
    request = CleanupRequest(
        product="demo", run_id=RUN_ID, dry_run=True, confirm_token=None, interactive=False
    )

    assert request.dry_run is True
