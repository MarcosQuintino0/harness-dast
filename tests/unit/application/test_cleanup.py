# ruff: noqa: S105, S608
"""Caso de uso `cleanup` sobre falsos: transação, confirmação, tetos, falhas e vazamentos."""

import json
from datetime import timedelta

import pytest

from harness_dast.application.cleanup import StatementFailed
from harness_dast.domain.cleanup_confirmation import CONFIRMATION_TTL
from harness_dast.domain.errors import CleanupError, ConfigError, ScopeViolation
from harness_dast.domain.profile import ProductProfile
from tests.fakes.cleanup_rig import (
    RUN_ID,
    SCRIPT,
    SECRETS,
    STARTED,
    CleanupRig,
    cleanup_profile,
)
from tests.fakes.profile_data import valid_profile_data

SECRET_VALUES = [value for key, value in SECRETS.items() if key != "ACME_USER_A_SENHA"]


def assert_nothing_opened(rig: CleanupRig) -> None:
    assert rig.database.opened == []
    assert rig.database.commits == 0
    assert rig.runs.audit == []


# ------------------------------------------------------------------ --dry-run


def test_dry_run_always_rolls_back_reports_counts_and_issues_a_token() -> None:
    rig = CleanupRig()

    report = rig.run(dry_run=True)

    assert report.status == "dry_run"
    assert (report.committed, report.rolled_back) == (False, True)
    assert [(s.index, s.table, s.rows) for s in report.statements] == [
        (1, "ITEM", 3),
        (2, "PEDIDO", 2),
    ]
    assert report.total_rows == 5
    assert report.confirmation_method == "none"
    assert rig.database.commits == 0
    assert rig.database.committed == {"PEDIDO": 10, "ITEM": 20}
    assert report.confirmation_token == "tok-1"
    assert rig.runs.confirmation is not None
    assert rig.runs.confirmation.rows_ceiling == 5
    assert report.token_expires_at is not None


def test_dry_run_serialization_never_contains_the_token() -> None:
    rig = CleanupRig()

    report = rig.run(dry_run=True)

    assert "tok-1" not in report.model_dump_json()
    assert "tok-1" not in json.dumps(report.model_dump(mode="json"))
    assert "tok-1" not in repr(report)
    assert "tok-1" not in rig.runs.serialized()


def test_dry_run_does_not_need_a_terminal_nor_a_confirmation() -> None:
    rig = CleanupRig()

    rig.run(dry_run=True, interactive=False)

    assert rig.prompt.plans == []


def test_dry_run_and_confirm_together_are_refused_before_connecting() -> None:
    rig = CleanupRig()

    with pytest.raises(ConfigError, match="não combinam"):
        rig.run(dry_run=True, confirm="tok-1")

    assert_nothing_opened(rig)


def test_dry_run_over_the_ceiling_rolls_back_fails_and_issues_no_token() -> None:
    rig = CleanupRig(profile=cleanup_profile(max_rows=4))

    with pytest.raises(CleanupError, match="acima do teto de 4"):
        rig.run(dry_run=True)

    assert rig.database.commits == 0
    assert rig.database.rollbacks >= 1
    assert rig.runs.confirmation is None
    assert rig.runs.records[-1].status == "failed"


# ------------------------------------------------------- confirmação interativa


def test_interactive_yes_commits_after_showing_the_plan() -> None:
    rig = CleanupRig(prompt_answer=True)

    report = rig.run(interactive=True)

    assert report.status == "committed"
    assert (report.committed, report.rolled_back) == (True, False)
    assert report.confirmation_method == "interactive"
    assert rig.database.commits == 1
    assert rig.database.committed == {"PEDIDO": 8, "ITEM": 17}
    assert [p.total_rows for p in rig.prompt.plans] == [5]
    assert rig.prompt.plans[0].script_sha256 == report.script_sha256


def test_interactive_no_rolls_back_and_never_commits() -> None:
    rig = CleanupRig(prompt_answer=False)

    report = rig.run(interactive=True)

    assert report.status == "declined"
    assert (report.committed, report.rolled_back) == (False, True)
    assert rig.database.commits == 0
    assert rig.database.committed == {"PEDIDO": 10, "ITEM": 20}


def test_interrupt_while_the_person_decides_closes_the_session_without_commit() -> None:
    rig = CleanupRig()

    class Interrupted:
        def confirm(self, plan: object) -> bool:
            raise KeyboardInterrupt

    rig.use_case._prompt = Interrupted()

    with pytest.raises(KeyboardInterrupt):
        rig.run(interactive=True)

    assert rig.database.commits == 0
    assert rig.database.closed == 1


def test_without_terminal_and_without_token_nothing_is_executed() -> None:
    rig = CleanupRig()

    with pytest.raises(ConfigError, match="Sem terminal interativo"):
        rig.run()

    assert_nothing_opened(rig)


# ------------------------------------------------------------ token de uso único


def dry_run_token(rig: CleanupRig) -> str:
    token = rig.run(dry_run=True).confirmation_token
    assert token is not None
    return token


def test_token_from_a_dry_run_allows_a_non_interactive_commit() -> None:
    rig = CleanupRig()
    token = dry_run_token(rig)

    report = rig.run(confirm=token)

    assert report.status == "committed"
    assert report.confirmation_method == "token"
    assert rig.database.commits == 1
    assert rig.prompt.plans == []


def test_token_is_single_use() -> None:
    rig = CleanupRig()
    token = dry_run_token(rig)
    rig.run(confirm=token)

    with pytest.raises(ConfigError, match="Não há token"):
        rig.run(confirm=token)

    assert rig.database.commits == 1


def test_wrong_token_is_refused_before_connecting_and_keeps_the_real_one() -> None:
    rig = CleanupRig()
    token = dry_run_token(rig)
    opened_before = len(rig.database.opened)

    with pytest.raises(ConfigError, match="não confere"):
        rig.run(confirm="tok-errado")

    assert len(rig.database.opened) == opened_before
    assert rig.run(confirm=token).status == "committed"


def test_token_expires_after_the_ttl() -> None:
    rig = CleanupRig()
    token = dry_run_token(rig)
    rig.clock.advance((CONFIRMATION_TTL + timedelta(seconds=1)).total_seconds())

    with pytest.raises(ConfigError, match="venceu"):
        rig.run(confirm=token)

    assert rig.database.commits == 0


def test_token_is_bound_to_the_script_that_the_person_saw() -> None:
    rig = CleanupRig()
    token = dry_run_token(rig)
    rig.scripts.content = (SCRIPT + "DELETE FROM ITEM WHERE RUN_ID = :run_id;").encode()

    with pytest.raises(ConfigError, match="script de limpeza mudou"):
        rig.run(confirm=token)

    assert rig.database.commits == 0


def test_token_issued_for_another_run_is_refused() -> None:
    rig = CleanupRig()
    token = dry_run_token(rig)
    assert rig.runs.confirmation is not None
    rig.runs.confirmation = rig.runs.confirmation.model_copy(update={"run_id": "outra-execucao"})

    with pytest.raises(ConfigError, match="outro produto ou outra execução"):
        rig.run(confirm=token)


def test_rows_above_what_the_person_saw_roll_back_with_exit_7_error() -> None:
    rig = CleanupRig()
    token = dry_run_token(rig)
    rig.database.matches[1] = 4  # apareceu lixo novo depois do --dry-run

    with pytest.raises(CleanupError, match="acima do teto de 5"):
        rig.run(confirm=token)

    assert rig.database.commits == 0
    assert rig.database.committed == {"PEDIDO": 10, "ITEM": 20}
    assert rig.runs.records[-1].status == "failed"


def test_fewer_rows_than_the_person_saw_are_fine() -> None:
    rig = CleanupRig()
    token = dry_run_token(rig)
    rig.database.matches[1] = 1

    assert rig.run(confirm=token).status == "committed"


# ----------------------------------------------------------- tetos e falhas


def test_profile_ceiling_rolls_back_even_with_a_valid_token() -> None:
    rig = CleanupRig(profile=cleanup_profile(max_rows=5))
    token = dry_run_token(rig)
    rig.database.matches[1] = 4

    with pytest.raises(CleanupError, match=r"cleanup.max_rows"):
        rig.run(confirm=token)

    assert rig.database.commits == 0


def test_statement_failure_rolls_back_and_names_index_and_table_only() -> None:
    rig = CleanupRig(prompt_answer=True)
    rig.database.fail_at = 2

    with pytest.raises(StatementFailed) as caught:
        rig.run(interactive=True)

    assert (caught.value.index, caught.value.table) == (2, "PEDIDO")
    assert "comando 2" in caught.value.message
    assert "PEDIDO" in caught.value.message
    assert caught.value.exit_code == 7
    assert rig.database.commits == 0
    assert rig.database.closed == 1
    assert rig.prompt.plans == []
    record = rig.runs.records[-1]
    assert (record.status, record.failed_statement, record.failed_table) == ("failed", 2, "PEDIDO")
    assert record.error_code == "CLEANUP_FAILED"
    assert record.rolled_back is True


def test_connection_failure_is_a_cleanup_error_with_a_record_and_no_session_to_close() -> None:
    rig = CleanupRig()
    rig.database.fail_open = True

    with pytest.raises(CleanupError, match="conectar"):
        rig.run(dry_run=True)

    assert rig.database.closed == 0
    assert rig.runs.records[-1].status == "failed"
    assert [line.event for line in rig.runs.audit] == ["started", "finished"]


def test_commit_failure_is_reported_as_failure_with_a_rollback_attempt() -> None:
    rig = CleanupRig()
    rig.database.fail_commit = True

    with pytest.raises(CleanupError, match="confirmar"):
        rig.run(interactive=True)

    record = rig.runs.records[-1]
    assert (record.status, record.committed) == ("failed", False)
    assert rig.database.rollbacks >= 1
    assert rig.database.committed == {"PEDIDO": 10, "ITEM": 20}


# ------------------------------------------------------- pré-condições


def test_unknown_run_is_refused_before_connecting() -> None:
    rig = CleanupRig()

    with pytest.raises(ConfigError, match="não foi encontrada"):
        rig.run(dry_run=True, run_id="2020-01-01T00-00-00Z-demo-aaaa")

    assert_nothing_opened(rig)


def test_invalid_run_id_is_refused() -> None:
    with pytest.raises(ConfigError, match="inválido"):
        CleanupRig().run(dry_run=True, run_id="../../etc")


def test_run_of_another_product_is_refused() -> None:
    rig = CleanupRig()
    assert rig.runs.manifest is not None
    rig.runs.manifest = rig.runs.manifest.model_copy(update={"product": "outro"})

    with pytest.raises(ConfigError, match="outro produto"):
        rig.run(dry_run=True)

    assert_nothing_opened(rig)


def test_run_still_in_progress_is_refused() -> None:
    rig = CleanupRig(finished_at=None)
    rig.clock.advance(-(rig.clock.now() - STARTED).total_seconds() + 60)  # 1 min depois do início

    with pytest.raises(ConfigError, match="em andamento"):
        rig.run(dry_run=True)

    assert_nothing_opened(rig)


def test_interrupted_run_without_end_is_cleanable_after_its_deadline() -> None:
    rig = CleanupRig(finished_at=None)  # relógio: 2 h depois do início; prazo do probe: 60 min

    assert rig.run(dry_run=True).status == "dry_run"


def test_expired_authorization_is_refused_before_connecting() -> None:
    rig = CleanupRig(profile=cleanup_profile(valid_until="2026-11-01"))

    with pytest.raises(ScopeViolation):
        rig.run(dry_run=True)

    assert_nothing_opened(rig)


def test_closed_execution_window_does_not_block_the_cleanup() -> None:
    # Terça-feira 12:00 UTC; a única janela abre às segundas de madrugada.
    rig = CleanupRig(profile=cleanup_profile(window="seg 03:00-04:00 UTC"))

    assert rig.run(dry_run=True).status == "dry_run"


def test_profile_without_cleanup_block_or_required_fields_says_what_to_add() -> None:
    without_block = ProductProfile.from_data(valid_profile_data("demo"))
    with pytest.raises(ConfigError, match="não tem o bloco cleanup"):
        CleanupRig(profile=without_block).run(dry_run=True)

    bare = ProductProfile.from_data(
        {
            **valid_profile_data("demo"),
            "cleanup": {
                "type": "oracle_sql",
                "script": "./cleanup/cleanup.sql",
                "connection": {"secret_ref": "env:ACME_ORACLE_DSN"},
                "requires_confirmation": True,
            },
        }
    )
    rig = CleanupRig(profile=bare)
    with pytest.raises(ConfigError) as caught:
        rig.run(dry_run=True)
    for name in ("cleanup.user", "cleanup.password", "cleanup.allowed_tables", "cleanup.max_rows"):
        assert name in caught.value.message
    assert_nothing_opened(rig)


def test_rejected_script_stops_before_secrets_and_connection() -> None:
    rig = CleanupRig()
    rig.scripts.content = b"DELETE FROM PEDIDO;"

    with pytest.raises(ConfigError, match="sem WHERE"):
        rig.run(dry_run=True)

    assert_nothing_opened(rig)


def test_table_outside_the_profile_allowlist_is_refused_before_connecting() -> None:
    rig = CleanupRig(profile=cleanup_profile(allowed_tables=["PEDIDO"]))

    with pytest.raises(ConfigError, match="allowed_tables"):
        rig.run(dry_run=True)

    assert_nothing_opened(rig)


def test_missing_secret_names_the_field_not_the_variable_or_value() -> None:
    rig = CleanupRig(secrets={k: v for k, v in SECRETS.items() if k != "ACME_ORACLE_DSN"})

    with pytest.raises(ConfigError) as caught:
        rig.run(dry_run=True)

    assert "cleanup.connection" in caught.value.message
    assert "ACME_ORACLE_DSN" not in caught.value.message
    assert_nothing_opened(rig)


# --------------------------------------------------------- variáveis e vazamento


def test_each_statement_receives_only_the_binds_it_uses_with_the_contract_values() -> None:
    rig = CleanupRig()

    rig.run(dry_run=True)

    first, second = rig.database.executed
    assert first == (1, {"run_id": RUN_ID})
    index, binds = second
    assert index == 2
    assert set(binds) == {"run_start", "account_1"}
    assert binds["account_1"] == SECRETS["ACME_USER_A_LOGIN"]
    assert binds["run_start"] == STARTED.replace(tzinfo=None)


def test_connection_receives_credentials_timeouts_and_schema() -> None:
    rig = CleanupRig(profile=cleanup_profile(db_schema="app"))

    rig.run(dry_run=True)

    connection = rig.database.opened[0]
    assert connection.dsn == SECRETS["ACME_ORACLE_DSN"]
    assert connection.user == SECRETS["ACME_ORACLE_USER"]
    assert connection.password.get_secret_value() == SECRETS["ACME_ORACLE_PASSWORD"]
    assert connection.db_schema == "APP"
    assert 0 < connection.connect_timeout_seconds <= 60
    assert 0 < connection.call_timeout_seconds <= 600
    assert SECRETS["ACME_ORACLE_PASSWORD"] not in repr(connection)


def test_nothing_written_or_returned_contains_credentials_or_bind_values() -> None:
    rig = CleanupRig()

    _exercise(rig)

    outputs = [rig.runs.serialized(), *(record.model_dump_json() for record in rig.runs.records)]
    for text in outputs:
        for secret in SECRET_VALUES:
            assert secret not in text


def _exercise(rig: CleanupRig) -> None:
    report = rig.run(dry_run=True)
    assert report.confirmation_token is not None
    rig.run(confirm=report.confirmation_token)
    rig.database.fail_at = 1
    with pytest.raises(CleanupError) as caught:
        rig.run(dry_run=True)
    for secret in SECRET_VALUES:
        assert secret not in caught.value.message
        assert secret not in (caught.value.hint or "")


def test_secrets_are_registered_so_logs_mask_them() -> None:
    rig = CleanupRig()

    rig.run(dry_run=True)

    masked = rig.vault.mask(" ".join(SECRET_VALUES))
    for secret in SECRET_VALUES:
        assert secret not in masked


def test_audit_has_started_before_finished_with_status_and_totals_only() -> None:
    rig = CleanupRig()

    rig.run(dry_run=True)

    started, finished = rig.runs.audit
    assert (started.event, finished.event) == ("started", "finished")
    assert started.status is None
    assert (finished.status, finished.total_rows, finished.mode) == ("dry_run", 5, "dry_run")
    assert started.script_sha256 == finished.script_sha256


def test_record_has_hash_tables_counts_and_timings() -> None:
    rig = CleanupRig()

    report = rig.run(interactive=True)

    record = rig.runs.records[-1]
    assert record.script_sha256 == report.script_sha256
    assert record.statement_count == 2
    assert record.tables == ("ITEM", "PEDIDO")
    assert record.max_rows == 100
    assert record.finished_at >= record.started_at


def test_rollback_failure_after_an_error_is_recorded_as_not_rolled_back() -> None:
    rig = CleanupRig()
    rig.database.fail_at = 1
    rig.database.fail_rollback = True

    with pytest.raises(StatementFailed):
        rig.run(dry_run=True)

    assert rig.runs.records[-1].rolled_back is False
    assert rig.database.closed == 1


def test_token_consumed_by_someone_else_in_the_meantime_is_refused() -> None:
    rig = CleanupRig()
    token = dry_run_token(rig)
    rig.runs.consume_confirmation = lambda run_id: False  # type: ignore[method-assign]  # corrida

    with pytest.raises(ConfigError, match="já foi usado"):
        rig.run(confirm=token)

    assert rig.database.commits == 0


def test_api_key_profile_has_no_account_binds_so_a_script_using_them_is_refused() -> None:
    data = valid_profile_data("demo", with_cleanup=True)
    data["auth"] = {
        "type": "api_key",
        "header_name": "X-API-Key",
        "accounts": [
            {"alias": "svc", "role": "servico", "api_key": {"secret_ref": "env:ACME_KEY"}}
        ],
    }
    data["cleanup"] = {**cleanup_profile().cleanup.model_dump(mode="json"), "type": "oracle_sql"}  # type: ignore[union-attr]
    rig = CleanupRig(profile=ProductProfile.from_data(data))

    with pytest.raises(ConfigError, match="contrato"):
        rig.run(dry_run=True)

    assert_nothing_opened(rig)
