"""Executor de limpeza em Oracle com python-oracledb em modo thin (implementa `CleanupExecutor`).

Modo thin: o driver fala o protocolo do Oracle sozinho, sem instalar o cliente Oracle na máquina.
Uma conexão = UMA transação, sem confirmação automática; `SET TRANSACTION` nomeia a transação
para quem olhar `V$TRANSACTION`. Todo erro do driver vira `CleanupError` que cita só o CÓDIGO
(`ORA-02292`, `DPY-6005`): o texto do driver pode trazer host, usuário ou dado da linha e por
isso nunca é repassado.
"""

import re
from collections.abc import Mapping
from contextlib import suppress

import oracledb

from harness_dast.application.ports import CleanupConnection, CleanupSession
from harness_dast.domain.cleanup_binds import BindValue
from harness_dast.domain.cleanup_gate import CleanupStatement
from harness_dast.domain.errors import CleanupError

_ERROR_CODE = re.compile(r"\b(?:ORA|DPY|DPI)-\d{4,5}\b")
_SCHEMA = re.compile(r"[A-Z][A-Z0-9_$#]{0,29}")
_SET_TRANSACTION = "SET TRANSACTION READ WRITE NAME 'hdast_cleanup'"


def _database_error(action: str, error: oracledb.Error) -> CleanupError:
    match = _ERROR_CODE.search(str(error))
    code = match.group(0) if match else "sem código"
    return CleanupError(
        f"Erro do banco ao {action} ({code}).",
        hint="Consulte o código no manual do Oracle; o detalhe do driver não é exibido.",
    )


class OracleSession:
    """Uma transação aberta em uma conexão Oracle."""

    def __init__(self, connection: oracledb.Connection) -> None:
        """Guarda a conexão já aberta e com a transação iniciada."""
        self._connection = connection

    def execute(self, statement: CleanupStatement, binds: Mapping[str, BindValue]) -> int:
        """Executa o comando e devolve as linhas afetadas."""
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(statement.sql, dict(binds))
                return int(cursor.rowcount)
        except oracledb.Error as error:
            raise _database_error("executar o comando", error) from None

    def commit(self) -> None:
        """Confirma a transação."""
        try:
            self._connection.commit()
        except oracledb.Error as error:
            raise _database_error("confirmar a transação", error) from None

    def rollback(self) -> None:
        """Desfaz a transação."""
        try:
            self._connection.rollback()
        except oracledb.Error as error:
            raise _database_error("desfazer a transação", error) from None

    def close(self) -> None:
        """Encerra a conexão; o que não foi confirmado é desfeito pelo servidor."""
        # Falha ao fechar não muda o resultado: a conexão já não é usada e o Oracle descarta a
        # transação aberta quando a sessão termina.
        with suppress(oracledb.Error):
            self._connection.close()


class OracleCleanupExecutor:
    """Abre conexões Oracle para a limpeza."""

    def open(self, connection: CleanupConnection) -> CleanupSession:
        """Conecta, aplica o esquema (se houver), o tempo limite de chamada e inicia a transação."""
        try:
            raw = oracledb.connect(
                user=connection.user,
                password=connection.password.get_secret_value(),
                dsn=connection.dsn,
                tcp_connect_timeout=float(connection.connect_timeout_seconds),
            )
        except oracledb.Error as error:
            raise _database_error("conectar", error) from None
        session = OracleSession(raw)
        try:
            raw.autocommit = False
            raw.call_timeout = connection.call_timeout_seconds * 1000
            self._prepare(raw, connection.db_schema)
        except oracledb.Error as error:
            session.close()
            raise _database_error("preparar a sessão", error) from None
        except CleanupError:
            session.close()
            raise
        return session

    @staticmethod
    def _prepare(raw: oracledb.Connection, db_schema: str | None) -> None:
        with raw.cursor() as cursor:
            if db_schema is not None:
                if not _SCHEMA.fullmatch(db_schema):
                    raise CleanupError("Esquema de limpeza inválido.", hint="Revise db_schema.")
                # Identificador validado acima: não há valor livre no comando.
                cursor.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {db_schema}")
            cursor.execute(_SET_TRANSACTION)
