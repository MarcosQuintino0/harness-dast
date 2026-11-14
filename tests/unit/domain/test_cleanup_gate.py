# ruff: noqa: S608
"""Portão do SQL de limpeza: o que aceita e cada construção que recusa."""

import hashlib

import pytest

from harness_dast.domain.cleanup_gate import (
    MAX_SCRIPT_BYTES,
    MAX_STATEMENTS,
    CleanupPolicy,
    parse_cleanup_script,
)
from harness_dast.domain.errors import ConfigError

POLICY = CleanupPolicy(allowed_tables=frozenset({"PEDIDO", "ITEM", "APP.LOG"}), account_count=2)
ANCHOR = "CREATED_AT >= :run_start"
GOOD = f"DELETE FROM PEDIDO WHERE {ANCHOR} AND CREATED_BY IN (:account_1, :account_2);"


def parse(script: str | bytes, policy: CleanupPolicy = POLICY):  # type: ignore[no-untyped-def]
    raw = script.encode("utf-8") if isinstance(script, str) else script
    return parse_cleanup_script(raw, policy)


def refused(script: str | bytes) -> str:
    with pytest.raises(ConfigError) as caught:
        parse(script)
    return caught.value.message


# ------------------------------------------------------------------ aceitos


def test_accepts_delete_with_anchor_and_reports_tables_binds_and_hash() -> None:
    script = parse(GOOD)

    assert len(script.statements) == 1
    statement = script.statements[0]
    assert (statement.index, statement.table) == (1, "PEDIDO")
    assert statement.binds == ("run_start", "account_1", "account_2")
    assert script.sha256 == hashlib.sha256(GOOD.encode()).hexdigest()
    assert script.tables == ("PEDIDO",)


def test_accepts_the_real_pilot_script() -> None:
    from pathlib import Path

    path = Path(__file__).parents[3] / "lab" / "pilot" / "cleanup" / "cleanup.sql"
    policy = CleanupPolicy(
        allowed_tables=frozenset({"RECEITA", "CONSULTA", "PACIENTE", "MEDICO", "CONVENIO"}),
        account_count=4,
    )

    script = parse_cleanup_script(path.read_bytes(), policy)

    assert [s.table for s in script.statements] == [
        "RECEITA",
        "CONSULTA",
        "PACIENTE",
        "MEDICO",
        "CONVENIO",
    ]


@pytest.mark.parametrize(
    "script",
    [
        "delete from pedido where created_at >= :RUN_START and created_by in (:Account_1);",
        f"DeLeTe FrOm PeDiDo WhErE {ANCHOR};",
        "DELETE FROM PEDIDO P WHERE P.CREATED_AT >= :run_start;",
        f"DELETE FROM APP.LOG WHERE {ANCHOR};",
        f"DELETE FROM PEDIDO WHERE {ANCHOR}",  # último comando sem ponto e vírgula
        f"DELETE FROM PEDIDO WHERE {ANCHOR};;\n;",  # vazios são ignorados
        f"DELETE FROM PEDIDO WHERE ({ANCHOR} AND STATUS = 'A');",  # parênteses de fora
        f"DELETE FROM PEDIDO WHERE STATUS BETWEEN 1 AND 2 AND {ANCHOR};",
        "DELETE FROM PEDIDO WHERE RUN_TAG LIKE '%' || :run_tag || '%';",
        "DELETE FROM PEDIDO WHERE RUN_ID = :run_id AND UPPER(NOME) = 'X';",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND ID IN (SELECT PEDIDO_ID FROM ITEM WHERE X = 1);",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND EXISTS (SELECT 1 FROM ITEM I, APP.LOG L);",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND ID IN (SELECT 1 FROM DUAL);",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND ID IN (SELECT 1 FROM ITEM JOIN APP.LOG ON ID = X);",
        f"\ufeffDELETE FROM PEDIDO WHERE {ANCHOR};",  # BOM do Windows
        f"DELETE FROM PEDIDO\r\n WHERE {ANCHOR};\r\n",
    ],
)
def test_accepts_valid_forms(script: str) -> None:
    assert len(parse(script).statements) >= 1


def test_executes_the_tokens_without_comments_so_what_runs_is_what_was_checked() -> None:
    script = parse(
        "-- cabeçalho\nDELETE /*+ hint */ FROM PEDIDO -- tabela\n"
        f"WHERE {ANCHOR} /* ; DROP TABLE X */ ;"
    )

    assert script.statements[0].sql == f"DELETE FROM PEDIDO WHERE {ANCHOR}"


def test_numbers_statements_and_lists_distinct_tables_in_order() -> None:
    script = parse(
        f"DELETE FROM ITEM WHERE {ANCHOR}; DELETE FROM PEDIDO WHERE {ANCHOR};"
        f"DELETE FROM ITEM WHERE RUN_ID = :run_id;"
    )

    assert [s.index for s in script.statements] == [1, 2, 3]
    assert script.tables == ("ITEM", "PEDIDO")


# ------------------------------------------------- comandos que não são DELETE


@pytest.mark.parametrize(
    ("script", "fragment"),
    [
        ("TRUNCATE TABLE PEDIDO;", "TRUNCATE"),
        ("DROP TABLE PEDIDO;", "DROP"),
        ("ALTER TABLE PEDIDO ADD X NUMBER;", "ALTER"),
        ("CREATE TABLE X (A NUMBER);", "CREATE"),
        ("GRANT DELETE ON PEDIDO TO X;", "GRANT"),
        ("REVOKE DELETE ON PEDIDO FROM X;", "REVOKE"),
        ("MERGE INTO PEDIDO USING DUAL ON (1=1) WHEN MATCHED THEN DELETE;", "MERGE"),
        ("INSERT INTO PEDIDO VALUES (1);", "INSERT"),
        ("UPDATE PEDIDO SET X = 1 WHERE CREATED_AT >= :run_start;", "UPDATE"),
        ("COMMIT;", "transação"),
        ("ROLLBACK;", "transação"),
        ("SAVEPOINT a;", "transação"),
        ("BEGIN NULL; END;", "PL/SQL"),
        ("DECLARE X NUMBER; BEGIN NULL; END;", "PL/SQL"),
        ("EXECUTE IMMEDIATE 'DROP TABLE X';", "EXECUTE"),
        ("EXEC proc;", "EXEC"),
        ("CALL proc();", "CALL"),
        ("SELECT * FROM PEDIDO;", "SELECT"),
        ("SET ROLE ALL;", "SET"),
        ("LOCK TABLE PEDIDO IN EXCLUSIVE MODE;", "LOCK"),
        ("PROMPT oi;", "só DELETE"),
        ("/", "não começa por DELETE"),
        ("(DELETE FROM PEDIDO WHERE 1 = 1);", "não começa por DELETE"),
    ],
)
def test_rejects_statements_that_are_not_delete(script: str, fragment: str) -> None:
    assert fragment in refused(script)


def test_rejects_plsql_block_that_wraps_a_valid_delete() -> None:
    message = refused(f"BEGIN DELETE FROM PEDIDO WHERE {ANCHOR}; COMMIT; END;")

    assert "PL/SQL" in message


def test_rejects_second_dangerous_statement_after_a_valid_one() -> None:
    message = refused(f"DELETE FROM PEDIDO WHERE {ANCHOR} AND X = 'a'; DROP TABLE T; --'")

    assert "Comando 2" in message
    assert "DROP" in message


@pytest.mark.parametrize(
    "script",
    [
        "DELETE FROM PEDIDO;",
        "DELETE FROM PEDIDO",
        "DELETE FROM PEDIDO -- WHERE CREATED_AT >= :run_start\n;",
        "DELETE FROM PEDIDO /* WHERE CREATED_AT >= :run_start */;",
        "DELETE PEDIDO WHERE CREATED_AT >= :run_start;",
        "DELETE FROM PEDIDO PARTITION (P1) WHERE CREATED_AT >= :run_start;",
        "DELETE FROM PEDIDO, ITEM WHERE CREATED_AT >= :run_start;",
        "DELETE FROM (SELECT * FROM PEDIDO) WHERE CREATED_AT >= :run_start;",
        "DELETE FROM PEDIDO WHERE;",
    ],
)
def test_rejects_delete_without_a_usable_where(script: str) -> None:
    refused(script)


def test_says_where_is_missing_when_it_hides_in_a_comment() -> None:
    assert "sem WHERE" in refused("DELETE FROM PEDIDO /* WHERE CREATED_AT >= :run_start */;")


# ------------------------------------------------- condição sem amarração


@pytest.mark.parametrize(
    "where",
    [
        "1 = 1",
        "1=1",
        "'a' = 'a'",
        "1 = 1 AND CREATED_AT >= :run_start",
        "CREATED_AT >= :run_start AND 2 > 1",
        "ID = ID",
        ":run_id = :run_id",
        "TRUE",
        "CREATED_AT >= :run_start OR 1 = 1",
    ],
)
def test_rejects_tautologies(where: str) -> None:
    refused(f"DELETE FROM PEDIDO WHERE {where};")


@pytest.mark.parametrize(
    "where",
    [
        "STATUS = 'X'",  # sem variável
        "ID > 0",
        "ID IS NOT NULL",
        "CREATED_AT >= :run_start OR STATUS = 'X'",  # o OR anula a amarração
        "STATUS = 'X' OR CREATED_AT >= :run_start",
        "NOT CREATED_BY = :account_1",
        "CREATED_BY <> :account_1",
        "CREATED_BY != :account_1",
        "CREATED_BY NOT IN (:account_1)",
        "CREATED_AT < :run_start",  # apagaria o que é ANTERIOR à execução
        "CREATED_AT <= :run_start",
        "CREATED_AT BETWEEN :run_start AND :run_start",
        "CREATED_BY IN (:account_1, 'x')",
        "CREATED_BY IN (SELECT USERNAME FROM ITEM)",
        "(CREATED_AT >= :run_start OR STATUS = 'X') AND ID > 0",
        "NOME LIKE '%'",
        "UPPER(CREATED_BY) = :account_1",  # coluna dentro de função não é amarração
        "ID IN (SELECT ID FROM ITEM WHERE CREATED_AT >= :run_start)",  # subconsulta
        "CREATED_AT >= :run_start - STATUS",  # coluna do lado das variáveis
        "CREATED_AT >= :run_start - 36500",  # aritmética alargaria a amarração
        "CREATED_AT >= (:run_start)",
        "CREATED_AT >= :run_start AND STATUS = 'A' OR STATUS = 'Z'",  # AND ata mais que OR
        "STATUS = 'Z' OR CREATED_AT >= :run_start AND STATUS = 'A'",
    ],
)
def test_rejects_where_without_a_tying_condition(where: str) -> None:
    assert "amarração" in refused(f"DELETE FROM PEDIDO WHERE {where};")


# -------------------------------------------------------------- tabelas


@pytest.mark.parametrize(
    "script",
    [
        f"DELETE FROM OUTRA WHERE {ANCHOR};",
        f"DELETE FROM OUTRO.PEDIDO WHERE {ANCHOR};",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND ID IN (SELECT ID FROM OUTRA);",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND ID IN (SELECT ID FROM ITEM, OUTRA);",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND ID IN (SELECT 1 FROM ITEM JOIN OUTRA ON ID = ID2);",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND ID IN (SELECT ID FROM SYS.USER$);",
        f"DELETE FROM LOG WHERE {ANCHOR};",  # só APP.LOG está na lista: sem esquema é outra
    ],
)
def test_rejects_tables_outside_the_allowlist(script: str) -> None:
    assert "allowed_tables" in refused(script)


def test_names_the_table_and_the_statement_in_the_message() -> None:
    message = refused(f"DELETE FROM PEDIDO WHERE {ANCHOR}; DELETE FROM OUTRA WHERE {ANCHOR};")

    assert "Comando 2" in message
    assert "OUTRA" in message


def test_rejects_inline_view_in_from_because_its_table_cannot_be_checked() -> None:
    script = f"DELETE FROM PEDIDO WHERE {ANCHOR} AND ID IN (SELECT ID FROM (SELECT 1 FROM OUTRA));"

    assert "nome de uma tabela" in refused(script)


# -------------------------------------------------------------- variáveis


@pytest.mark.parametrize(
    "bind",
    [":foo", ":account_3", ":account_0", ":account_", ":1", ":RUN", ":run_start2", ":ACCOUNT_01"],
)
def test_rejects_binds_outside_the_contract(bind: str) -> None:
    message = refused(f"DELETE FROM PEDIDO WHERE {ANCHOR} AND X = {bind};")

    assert "contrato" in message


@pytest.mark.parametrize(
    "fragment",
    [":", ":=", "::x", ':"x"', "&var", "&&var", "'&x'", "-- &x", "/* & */", "@link", "T@LINK"],
)
def test_rejects_substitution_dblink_and_loose_colons(fragment: str) -> None:
    refused(f"DELETE FROM PEDIDO WHERE {ANCHOR} AND X = {fragment};")


def test_rejects_dblink_in_the_table_name() -> None:
    refused(f"DELETE FROM PEDIDO@REMOTO WHERE {ANCHOR};")


def test_account_binds_depend_on_the_profile_account_count() -> None:
    one = CleanupPolicy(allowed_tables=frozenset({"PEDIDO"}), account_count=1)
    script = "DELETE FROM PEDIDO WHERE CREATED_BY IN (:account_1, :account_2);"

    with pytest.raises(ConfigError, match="contrato"):
        parse(script, one)
    assert parse(script, CleanupPolicy(allowed_tables=frozenset({"PEDIDO"}), account_count=2))


# -------------------------------------------------- funções e palavras


@pytest.mark.parametrize(
    "fragment",
    [
        "MINHA_FUNCAO(ID) = 1",
        "PKG.FUNCAO(ID) = 1",
        "DBMS_LOCK.SLEEP(1) = 1",
        "SYS_CONTEXT('A', 'B') = 'x'",
        "EXTRACT(YEAR FROM CREATED_AT) = 2026",
    ],
)
def test_rejects_unknown_or_packaged_function_calls(fragment: str) -> None:
    refused(f"DELETE FROM PEDIDO WHERE {ANCHOR} AND {fragment};")


@pytest.mark.parametrize(
    "fragment",
    [
        "ID IN (SELECT ID FROM ITEM FOR UPDATE)",
        "ID IN (SELECT ID INTO V FROM ITEM)",
        "X = 1 RETURNING ID INTO :run_id",
        "DBMS_OUTPUT = 1",
        "FLASHBACK = 1",
        "EXECUTE = 1",
        "COMMIT = 1",
        "ID = SELECT",
        "ID IN (SELECT ID FROM ITEM UNION SELECT ID FROM ITEM)",
    ],
)
def test_rejects_forbidden_words_inside_the_where(fragment: str) -> None:
    refused(f"DELETE FROM PEDIDO WHERE {ANCHOR} AND {fragment};")


def test_rejects_unbalanced_parentheses_and_trailing_slash() -> None:
    refused(f"DELETE FROM PEDIDO WHERE ({ANCHOR};")
    refused(f"DELETE FROM PEDIDO WHERE {ANCHOR});")
    refused(f"DELETE FROM PEDIDO WHERE {ANCHOR}\n/")


def test_allows_a_known_function_in_a_non_anchor_condition() -> None:
    assert parse(f"DELETE FROM PEDIDO WHERE {ANCHOR} AND NVL(STATUS, 'A') = 'A';")


# --------------------------------------------- comentários, textos, caracteres


def test_semicolon_inside_a_string_does_not_split_the_statement() -> None:
    script = parse(f"DELETE FROM PEDIDO WHERE {ANCHOR} AND NOME = 'x; DROP TABLE T; --';")

    assert len(script.statements) == 1
    assert "DROP TABLE T" in script.statements[0].sql  # continua dentro do texto


@pytest.mark.parametrize(
    "literal",
    [
        "q'[x'; DROP TABLE T; --]'",
        "Q'!x; DROP TABLE T; --!'",
        "nq'<x; DROP TABLE T;>'",
        "q'{x}'; DROP TABLE T; --}'",  # o fechamento é }' : o que vem depois é código
    ],
)
def test_q_literals_hide_semicolons_only_until_their_own_closing(literal: str) -> None:
    script = f"DELETE FROM PEDIDO WHERE {ANCHOR} AND NOME = {literal}"
    if "}'; DROP" in literal:
        refused(script)
    else:
        assert len(parse(script + ";").statements) == 1


def test_escaped_quote_does_not_end_a_string() -> None:
    script = parse(f"DELETE FROM PEDIDO WHERE {ANCHOR} AND NOME = 'l''a; DROP TABLE T; --';")

    assert len(script.statements) == 1
    assert script.statements[0].sql.endswith("NOME = 'l''a; DROP TABLE T; --'")  # um só texto


@pytest.mark.parametrize(
    "script",
    [
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND NOME = 'aberto;",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} /* aberto;",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND NOME = q'[aberto;",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND NOME = q' x';",
        f"DELETE FROM PEDIDO WHERE {ANCHOR} AND NOME = q'';",
        f'DELETE FROM "PEDIDO" WHERE {ANCHOR};',
        f'DELETE FROM PEDIDO WHERE {ANCHOR} AND "X" = 1;',
    ],
)
def test_rejects_unterminated_text_comments_and_quoted_identifiers(script: str) -> None:
    refused(script)


def test_nested_comment_ends_at_the_first_close_and_exposes_what_follows() -> None:
    message = refused(f"DELETE FROM PEDIDO WHERE {ANCHOR}; /* a /* b */ DROP TABLE T; */")

    assert "DROP" in message


def test_comment_with_semicolon_hides_nothing_dangerous() -> None:
    script = parse(f"DELETE FROM PEDIDO WHERE {ANCHOR} -- ; DROP TABLE T\n;")

    assert len(script.statements) == 1


@pytest.mark.parametrize(
    "script",
    [
        "DELETE FROM PEDIDO WHERE CREATED_AT >= :run_start; \uff24ROP TABLE T;",  # D largo
        "\u0415XEC proc;",  # E cirílico
        "DELETE FROM PEDID\u041e WHERE CREATED_AT >= :run_start;",  # O cirílico na tabela
        "DELETE FROM PEDIDO WHERE CREATED_AT >= :run_start AND X\u200b= 1;",  # espaço largura zero
        "DELETE FROM PEDIDO WHERE CREATED_AT >= :run_start AND X = 1\u037e",  # ';' grego
        "DELETE FROM PEDIDO WHERE CREATED_AT >= :run_start\u2028; DROP TABLE T;",
    ],
)
def test_rejects_non_ascii_outside_strings_and_comments(script: str) -> None:
    assert "ASCII" in refused(script)


def test_allows_non_ascii_inside_strings_and_comments() -> None:
    script = parse(f"-- ação\nDELETE FROM PEDIDO WHERE {ANCHOR} AND NOME = 'João';")

    assert len(script.statements) == 1


@pytest.mark.parametrize("control", ["\x00", "\x0b", "\x0c", "\x1b", "\x7f"])
def test_rejects_control_characters(control: str) -> None:
    refused(f"DELETE FROM PEDIDO WHERE {ANCHOR} -- {control}\n;")


def test_rejects_a_lone_carriage_return_that_could_end_a_comment_differently() -> None:
    refused(f"DELETE FROM PEDIDO -- oculto\r DROP TABLE T;\n WHERE {ANCHOR};")


# -------------------------------------------------------------- o arquivo


def test_rejects_empty_script_and_script_with_only_comments() -> None:
    assert "nenhum comando" in refused("")
    assert "nenhum comando" in refused("-- só comentário\n/* outro */")
    assert "nenhum comando" in refused(";;;")


def test_rejects_oversized_script() -> None:
    assert "KiB" in refused(b"-" * (MAX_SCRIPT_BYTES + 1))


def test_rejects_script_with_too_many_statements() -> None:
    script = (f"DELETE FROM PEDIDO WHERE {ANCHOR};" * (MAX_STATEMENTS + 1)).encode()

    assert "mais de" in refused(script)


def test_rejects_script_that_is_not_utf8() -> None:
    assert "UTF-8" in refused(b"DELETE FROM PEDIDO WHERE X = '\xe7\xe3';")


def test_error_messages_never_echo_literal_values() -> None:
    message = refused("DELETE FROM PEDIDO WHERE X = 'senha-secreta-123' AND NOME = :foo;")

    assert "senha-secreta-123" not in message


# ------------------------------------------- amarração por coluna real (ADR 0025)


@pytest.mark.parametrize(
    "condition",
    [
        "USER = :account_1",
        "ROWNUM >= :run_start",
        "UID = :run_id",
        "SESSIONTIMEZONE = :run_tag",
        "SYS_GUID = :run_id",
        "T.SYSDATE >= :run_start",
    ],
)
def test_refuses_an_anchor_that_does_not_depend_on_the_row(condition: str) -> None:
    refused(f"DELETE FROM PEDIDO WHERE {condition};")


@pytest.mark.parametrize(
    "condition",
    [
        "NOME >= :run_tag",
        "RUN_ID > :run_id",
        "CREATED_BY >= :account_1",
        "NOME >= :run_start || 'x'",
    ],
)
def test_refuses_a_range_anchor_against_anything_but_run_start(condition: str) -> None:
    refused(f"DELETE FROM PEDIDO WHERE {condition};")


@pytest.mark.parametrize(
    "condition",
    [
        "CREATED_AT >= :run_start",
        "CREATED_AT > :run_start",
        "RUN_TAG = :run_tag",
        "RUN_TAG LIKE '%' || :run_tag || '%'",
        "P.CREATED_BY IN (:account_1)",
    ],
)
def test_still_accepts_a_real_column_anchored_to_the_run(condition: str) -> None:
    assert parse(f"DELETE FROM PEDIDO P WHERE {condition};").statements


@pytest.mark.parametrize(
    "condition",
    [
        "RUN_ID = :run_id AND ID IN (SELECT SEQ.NEXTVAL FROM DUAL)",
        "RUN_ID = :run_id AND ID = SEQ.CURRVAL",
    ],
)
def test_refuses_sequence_pseudo_columns_because_nextval_has_a_side_effect(condition: str) -> None:
    refused(f"DELETE FROM PEDIDO WHERE {condition};")


@pytest.mark.parametrize("alias", ["DROP", "drop", "TRUNCATE", "GRANT", "UNION", "SELECT"])
def test_parse_cleanup_script_rejects_reserved_word_as_table_alias_quando_vem_antes_do_where(
    alias: str,
) -> None:
    script = (
        f"DELETE FROM PEDIDO {alias}/* ; DROP TABLE X; */WHERE CREATED_AT >= :run_start "
        "AND CREATED_BY IN (:account_1);"
    )

    with pytest.raises(ConfigError, match="não vale como apelido"):
        parse_cleanup_script(script.encode("utf-8"), POLICY)
