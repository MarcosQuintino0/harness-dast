"""Executor Oracle: tradução de erros do driver sem vazar detalhes.

O driver é substituído por um falso só para injetar falhas difíceis de provocar (credencial
inválida, restrição de integridade, queda na confirmação). O comportamento contra um Oracle de
verdade fica em `tests/integration/test_cleanup_oracle.py`.
"""

from typing import Any

import oracledb
import pytest
from pydantic import SecretStr

from harness_dast.adapters.cleanup.oracle_executor import OracleCleanupExecutor
from harness_dast.application.cleanup_ports import CleanupConnection
from harness_dast.domain.cleanup_gate import CleanupStatement
from harness_dast.domain.errors import CleanupError

PASSWORD = "senha-do-banco-SEGREDO"  # noqa: S105 - sentinela
USER = "usuario-SEGREDO"
LEAK = "SEGREDO_OWNER.FK_PEDIDO_ITEM"


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self._connection = connection
        self.rowcount = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, binds: dict[str, Any] | None = None) -> None:
        self._connection.executed.append((sql, binds))
        if self._connection.fail_sql is not None and sql.startswith(self._connection.fail_sql):
            raise oracledb.DatabaseError(
                f"ORA-02292: integrity constraint ({LEAK}) violated - valor={PASSWORD}"
            )
        self.rowcount = 7


class FakeConnection:
    def __init__(self) -> None:
        self.autocommit = True
        self.call_timeout = 0
        self.executed: list[tuple[str, dict[str, Any] | None]] = []
        self.fail_sql: str | None = None
        self.fail_commit = False
        self.fail_close = False
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        if self.fail_commit:
            raise oracledb.DatabaseError(f"ORA-03113: end-of-file on {LEAK}")
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        if self.fail_close:
            raise oracledb.DatabaseError("DPY-1001: connection is not connected")
        self.closed = True


def connection(db_schema: str | None = None) -> CleanupConnection:
    return CleanupConnection(
        dsn="oracle.interno:1521/TESTE",
        user=USER,
        password=SecretStr(PASSWORD),
        db_schema=db_schema,
        connect_timeout_seconds=9,
        call_timeout_seconds=30,
    )


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeConnection:
    instance = FakeConnection()
    calls: list[dict[str, Any]] = []

    def connect(**kwargs: Any) -> FakeConnection:
        calls.append(kwargs)
        return instance

    monkeypatch.setattr(oracledb, "connect", connect)
    instance.connect_calls = calls  # type: ignore[attr-defined]  # atributo só do teste
    return instance


def statement() -> CleanupStatement:
    return CleanupStatement(
        index=1, table="PEDIDO", sql="DELETE FROM PEDIDO WHERE X = :run_id", binds=("run_id",)
    )


def test_open_connects_with_timeouts_and_starts_a_named_transaction(fake: FakeConnection) -> None:
    OracleCleanupExecutor().open(connection())

    call = fake.connect_calls[0]  # type: ignore[attr-defined]
    assert (call["user"], call["password"], call["dsn"]) == (
        USER,
        PASSWORD,
        "oracle.interno:1521/TESTE",
    )
    assert call["tcp_connect_timeout"] == 9.0
    assert fake.autocommit is False
    assert fake.call_timeout == 30_000
    assert [sql for sql, _ in fake.executed] == ["SET TRANSACTION READ WRITE NAME 'hdast_cleanup'"]


def test_open_sets_the_current_schema_before_the_transaction(fake: FakeConnection) -> None:
    OracleCleanupExecutor().open(connection("APP"))

    assert [sql for sql, _ in fake.executed] == [
        "ALTER SESSION SET CURRENT_SCHEMA = APP",
        "SET TRANSACTION READ WRITE NAME 'hdast_cleanup'",
    ]


@pytest.mark.parametrize("schema", ["app; DROP TABLE X", "A B", "1APP", "a" * 31])
def test_open_refuses_a_schema_that_is_not_a_plain_identifier_and_closes(
    fake: FakeConnection, schema: str
) -> None:
    with pytest.raises(CleanupError, match="Esquema"):
        OracleCleanupExecutor().open(connection(schema))

    assert fake.closed is True
    assert fake.executed == []


def test_execute_passes_the_bind_values_and_returns_rowcount(fake: FakeConnection) -> None:
    session = OracleCleanupExecutor().open(connection())

    rows = session.execute(statement(), {"run_id": "r-1"})

    assert rows == 7
    assert fake.executed[-1] == ("DELETE FROM PEDIDO WHERE X = :run_id", {"run_id": "r-1"})


def test_driver_errors_become_cleanup_errors_with_the_code_only(fake: FakeConnection) -> None:
    session = OracleCleanupExecutor().open(connection())
    fake.fail_sql = "DELETE"

    with pytest.raises(CleanupError) as caught:
        session.execute(statement(), {"run_id": "r-1"})

    assert "ORA-02292" in caught.value.message
    for forbidden in (LEAK, PASSWORD, "r-1"):
        assert forbidden not in caught.value.message
        assert forbidden not in (caught.value.hint or "")


def test_connect_failure_never_echoes_driver_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(**kwargs: Any) -> None:
        raise oracledb.DatabaseError(f"DPY-6005: cannot connect to {USER}@oracle.interno:1521")

    monkeypatch.setattr(oracledb, "connect", refuse)

    with pytest.raises(CleanupError) as caught:
        OracleCleanupExecutor().open(connection())

    assert "DPY-6005" in caught.value.message
    assert USER not in caught.value.message
    assert "oracle.interno" not in caught.value.message


def test_error_without_a_known_code_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(**kwargs: Any) -> None:
        raise oracledb.InterfaceError("algo estranho")

    monkeypatch.setattr(oracledb, "connect", refuse)

    with pytest.raises(CleanupError, match="sem código"):
        OracleCleanupExecutor().open(connection())


def test_commit_and_rollback_are_forwarded_and_commit_errors_are_translated(
    fake: FakeConnection,
) -> None:
    session = OracleCleanupExecutor().open(connection())

    session.rollback()
    session.commit()
    fake.fail_commit = True
    with pytest.raises(CleanupError) as caught:
        session.commit()

    assert (fake.rollbacks, fake.commits) == (1, 1)
    assert "ORA-03113" in caught.value.message
    assert LEAK not in caught.value.message


def test_close_ignores_a_driver_failure(fake: FakeConnection) -> None:
    session = OracleCleanupExecutor().open(connection())
    fake.fail_close = True

    session.close()  # não levanta: a conexão já não é usada


def test_rollback_error_is_translated_with_the_code_only(fake: FakeConnection) -> None:
    session = OracleCleanupExecutor().open(connection())

    def broken() -> None:
        raise oracledb.DatabaseError(f"ORA-03114: not connected to {LEAK}")

    fake.rollback = broken  # type: ignore[method-assign]  # injeta a falha difícil de provocar

    with pytest.raises(CleanupError) as caught:
        session.rollback()

    assert "ORA-03114" in caught.value.message
    assert LEAK not in caught.value.message


def test_failure_while_preparing_the_session_closes_it_and_reports_the_code(
    fake: FakeConnection,
) -> None:
    fake.fail_sql = "SET TRANSACTION"

    with pytest.raises(CleanupError) as caught:
        OracleCleanupExecutor().open(connection())

    assert "preparar a sessão" in caught.value.message
    assert "ORA-02292" in caught.value.message
    assert fake.closed is True
