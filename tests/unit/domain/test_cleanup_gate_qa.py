# ruff: noqa: S608, S105, RUF001, E501
"""QA independente do portão de SQL da limpeza (`domain/cleanup_gate.py`).

Escrito a partir do docstring do módulo: só `DELETE FROM <tabela permitida> WHERE <condição>`,
com ao menos uma condição de AMARRAÇÃO à execução ligada por `AND` e só variáveis do contrato.
Os testes que falham de propósito demonstram defeitos; veja o parecer em
docs/arquivo/reviews/2026-11-13-qa-m2-m5.md.
"""

import pytest

from harness_dast.domain.cleanup_gate import (
    MAX_SCRIPT_BYTES,
    MAX_STATEMENTS,
    CleanupPolicy,
    CleanupScript,
    parse_cleanup_script,
)
from harness_dast.domain.errors import ConfigError

POLICY = CleanupPolicy(allowed_tables=frozenset({"ORDERS", "ITEMS", "HR.EMP"}), account_count=2)
ANCHOR = "TAG = :run_tag"


def parse(sql: str, policy: CleanupPolicy = POLICY) -> CleanupScript:
    return parse_cleanup_script(sql.encode("utf-8"), policy)


def refused(sql: str) -> bool:
    try:
        parse(sql)
    except ConfigError:
        return True
    return False


# --------------------------------------------------------------------- o que deve passar


@pytest.mark.parametrize(
    "sql",
    [
        f"DELETE FROM ORDERS WHERE {ANCHOR};",
        "DELETE FROM ORDERS WHERE CREATED_AT >= :run_start;",
        "DELETE FROM ORDERS WHERE CREATED_AT > :run_start AND CREATED_BY = :account_1;",
        "DELETE FROM ORDERS WHERE CREATED_BY IN (:account_1, :account_2);",
        "DELETE FROM ORDERS WHERE RUN_ID = :run_id;",
        f"DELETE FROM orders WHERE {ANCHOR};",
        f"DELETE FROM ORDERS o WHERE o.{ANCHOR};",
        f"DELETE FROM HR.EMP WHERE {ANCHOR};",
        f"DELETE FROM ORDERS WHERE NAME LIKE 'x%' AND {ANCHOR};",
        f"DELETE FROM ORDERS WHERE ID IN (SELECT ORDER_ID FROM ITEMS WHERE {ANCHOR}) AND {ANCHOR};",
        f"DELETE FROM ORDERS WHERE {ANCHOR} -- comentario\n;",
        f"DELETE FROM ORDERS /* nota */ WHERE {ANCHOR};",
    ],
)
def test_parse_accepts_deletes_bound_to_the_run_when_contract_is_followed(sql: str) -> None:
    script = parse(sql)

    assert len(script.statements) == 1


def test_parse_returns_sql_without_comments_when_script_has_comments() -> None:
    script = parse(f"DELETE FROM ORDERS /* ; DROP TABLE X */ WHERE {ANCHOR} -- ; TRUNCATE T\n;")

    sql = script.statements[0].sql.upper()

    assert "DROP" not in sql
    assert "TRUNCATE" not in sql
    assert "/*" not in sql
    assert "--" not in sql


def test_parse_reports_only_the_binds_used_when_statement_has_two_binds() -> None:
    script = parse("DELETE FROM ORDERS WHERE CREATED_AT >= :run_start AND CREATED_BY = :account_2;")

    assert set(script.statements[0].binds) == {"run_start", "account_2"}


def test_parse_hash_is_sha256_of_the_exact_bytes_when_script_is_accepted() -> None:
    import hashlib

    raw = f"DELETE FROM ORDERS WHERE {ANCHOR};".encode()

    assert parse_cleanup_script(raw, POLICY).sha256 == hashlib.sha256(raw).hexdigest()


# --------------------------------------------------------------------- o que deve ser recusado


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM ORDERS;",
        "DELETE FROM ORDERS WHERE 1 = 1;",
        "DELETE FROM ORDERS WHERE '1' = '1';",
        "DELETE FROM ORDERS WHERE ID = ID;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} OR 1 = 1;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} OR ID > 0;",
        f"DELETE FROM ORDERS WHERE (ID > 0 OR {ANCHOR});",
        f"DELETE FROM ORDERS WHERE NOT {ANCHOR};",
        "DELETE FROM ORDERS WHERE ID > 0;",
        "DELETE FROM ORDERS WHERE NAME LIKE '%';",
        "DELETE FROM ORDERS WHERE TAG IS NOT NULL;",
        "DELETE FROM ORDERS WHERE TAG = 'fixo';",
        "DELETE FROM ORDERS WHERE TAG = :run_tag - 1;",
        "DELETE FROM ORDERS WHERE CREATED_AT >= :run_start - 36500;",
        "TRUNCATE TABLE ORDERS;",
        "DROP TABLE ORDERS;",
        "UPDATE ORDERS SET X = 1 WHERE TAG = :run_tag;",
        "INSERT INTO ORDERS (X) VALUES (1);",
        "MERGE INTO ORDERS USING DUAL ON (1 = 1) WHEN MATCHED THEN DELETE;",
        "SELECT * FROM ORDERS;",
        "BEGIN DELETE FROM ORDERS WHERE TAG = :run_tag; END;",
        "COMMIT;",
        "ROLLBACK;",
        "DELETE FROM OTHER WHERE TAG = :run_tag;",
        "DELETE FROM SYS.USER$ WHERE TAG = :run_tag;",
        "DELETE FROM EMP WHERE TAG = :run_tag;",
        "DELETE FROM ORDERS@LINK WHERE TAG = :run_tag;",
        'DELETE FROM "ORDERS" WHERE TAG = :run_tag;',
        "DELETE FROM ORDERS WHERE TAG = &tag;",
        "DELETE FROM ORDERS WHERE TAG = :outra;",
        "DELETE FROM ORDERS WHERE TAG = :account_3;",
        "DELETE FROM ORDERS WHERE TAG = :1;",
        "DELETE FROM ORDERS WHERE TAG = :account_0;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} AND ID IN (SELECT ID FROM OTHER);",
        f"DELETE FROM ORDERS WHERE {ANCHOR} AND ID IN (SELECT ID FROM SYS.DUAL);",
        f"DELETE FROM ORDERS WHERE {ANCHOR} AND ID IN (SELECT ID FROM ITEMS@DBLINK);",
        f"DELETE FROM ORDERS WHERE {ANCHOR} AND F_QUALQUER(ID) = 1;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} AND PKG.FN(ID) = 1;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} AND DBMS_LOCK.SLEEP(1) = 1;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} AND UTL_HTTP.REQUEST('x') = 'a';",
        f"DELETE FROM ORDERS WHERE {ANCHOR} RETURNING ID INTO :x;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} AND ID IN (SELECT ID FROM ORDERS FOR UPDATE);",
        f"DELETE FROM ORDERS WHERE {ANCHOR}; DELETE FROM ORDERS;",
        f"DELETE FROM ORDERS WHERE {ANCHOR}; COMMIT;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} /",
        f"DELETE FROM ORDERS WHERE {ANCHOR}\r;",
        f"DELETE FROM ORDERS WHERE {ANCHOR}\x00;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} /* sem fim ;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} AND X = 'sem fim;",
        "DELETE FROM ORDERS WHERE TAG = :run_tag AND X = q'[sem fim;",
        "DELETE FROM ORDERS WHERE TAG = :run_tag AND Х = 1;",
        "DELETE FROM ORDERS WHERE TAG = :run_tag AND X := 1;",
        "",
        "-- so comentario\n",
        ";",
    ],
)
def test_parse_refuses_when_statement_violates_the_gate_contract(sql: str) -> None:
    assert refused(sql), sql


def test_parse_refuses_when_comment_hides_the_where_clause() -> None:
    assert refused("DELETE FROM ORDERS -- WHERE TAG = :run_tag\n;")
    assert refused("DELETE FROM ORDERS /* WHERE TAG = :run_tag */;")


def test_parse_refuses_whole_script_when_any_statement_is_invalid() -> None:
    sql = f"DELETE FROM ORDERS WHERE {ANCHOR};\nDELETE FROM ITEMS;\nDELETE FROM ORDERS WHERE {ANCHOR};"

    with pytest.raises(ConfigError) as caught:
        parse(sql)

    assert "2" in caught.value.message


def test_parse_refuses_when_script_exceeds_the_size_limit() -> None:
    filler = "-- " + "x" * MAX_SCRIPT_BYTES + "\n"

    assert refused(filler + f"DELETE FROM ORDERS WHERE {ANCHOR};")


def test_parse_refuses_when_script_has_too_many_statements() -> None:
    statement = f"DELETE FROM ORDERS WHERE {ANCHOR};\n"

    assert refused(statement * (MAX_STATEMENTS + 1))
    assert not refused(statement * MAX_STATEMENTS)


def test_parse_refuses_when_bytes_are_not_utf8() -> None:
    with pytest.raises(ConfigError):
        parse_cleanup_script(b"DELETE FROM ORDERS WHERE TAG = :run_tag; \xff\xfe", POLICY)


def test_parse_refuses_when_no_account_exists_for_account_bind() -> None:
    policy = CleanupPolicy(allowed_tables=frozenset({"ORDERS"}), account_count=0)

    with pytest.raises(ConfigError):
        parse_cleanup_script(b"DELETE FROM ORDERS WHERE CREATED_BY = :account_1;", policy)


def test_parse_errors_never_echo_literal_values_when_script_is_refused() -> None:
    secret = "valor-literal-secreto-123"
    with pytest.raises(ConfigError) as caught:
        parse(f"DELETE FROM ORDERS WHERE NAME = '{secret}';")

    assert secret not in caught.value.message
    assert secret not in (caught.value.hint or "")


# ----------------------------------------------- defeitos: amarração que não amarra nada
# O docstring promete que "nenhuma combinação ... consegue alargar o DELETE para além do que as
# variáveis da execução delimitam" e recusa "WHERE sem amarração". Pseudo-colunas do Oracle
# (SYSDATE, SYSTIMESTAMP, CURRENT_DATE...) não dependem da linha: `SYSDATE >= :run_start` é
# verdadeiro para TODAS as linhas, ou seja, um `WHERE 1 = 1` disfarçado.


@pytest.mark.parametrize(
    "condition",
    [
        "SYSDATE >= :run_start",
        "SYSDATE > :run_start",
        "SYSTIMESTAMP >= :run_start",
        "CURRENT_DATE >= :run_start",
        "CURRENT_TIMESTAMP > :run_start",
        "LOCALTIMESTAMP >= :run_start",
    ],
)
def test_parse_refuses_when_anchor_is_a_row_independent_pseudo_column(condition: str) -> None:
    assert refused(f"DELETE FROM ORDERS WHERE {condition};"), condition


# O contrato diz que a amarração delimita o DELETE "ao que as variáveis da execução delimitam".
# `>=`/`>` contra uma variável de TEXTO (run_id começa com o ano, 2026-...; run_tag e usuário de
# conta são texto) compara por ordem alfabética: `NAME >= :run_id` casa quase toda linha.


@pytest.mark.parametrize(
    "condition",
    [
        "NAME >= :run_id",
        "NAME > :run_id",
        "CREATED_BY >= :account_1",
        "CREATED_BY > :account_1",
        "TAG >= :run_tag",
        "TAG > :run_tag",
    ],
)
def test_parse_refuses_when_range_anchor_compares_text_binds(condition: str) -> None:
    assert refused(f"DELETE FROM ORDERS WHERE {condition};"), condition
