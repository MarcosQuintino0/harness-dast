# ruff: noqa: S608, RUF001, E501
"""QA independente da V1.4: formas de contrabandear comando perigoso pelo portão da limpeza."""

import pytest

from harness_dast.domain.cleanup_gate import CleanupPolicy, parse_cleanup_script
from harness_dast.domain.errors import HarnessError

POLICY = CleanupPolicy(allowed_tables=frozenset({"ORDERS", "ITEMS"}), account_count=2)
ANCHOR = "TAG = :run_tag"


def _refused(sql: str) -> bool:
    try:
        parse_cleanup_script(sql.encode("utf-8"), POLICY)
    except HarnessError:
        return True
    return False


@pytest.mark.parametrize(
    "sql",
    [
        f'DELETE FROM ORDERS "AND" WHERE {ANCHOR};',
        f'DELETE FROM ORDERS "WHERE" WHERE {ANCHOR};',
        f"DELETE FROM ORDERS AS o WHERE {ANCHOR};",
        f"DELETE FROM ORDERS OR WHERE {ANCHOR};",
        f"DELETE FROM ORDERS INTO WHERE {ANCHOR};",
        f"DELETE FROM ORDERS SELECT WHERE {ANCHOR};",
        f"DELETE FROM ORDERS SET WHERE {ANCHOR};",
        f"DELETE FROM ORDERS UNION WHERE {ANCHOR};",
        f"DELETE FROM ORDERS RETURNING WHERE {ANCHOR};",
        f"DELETE FROM ORDERS WHERE WHERE {ANCHOR};",
        f"DELETE FROM ORDERS WHERE {ANCHOR} -- x\nOR ID > 0;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} --\n OR 1=1;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} --\r OR 1=1;",
        f"DELETE FROM ORDERS WHERE {ANCHOR}\nOR\n1=1;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} /* /* */ OR 1=1 */;",
        f"DELETE FROM ORDERS WHERE {ANCHOR} /* ;",
        "DELETE FROM ORDERS WHERE A = 1 OR B = 2 AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE ID > 0 OR TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE (TAG = :run_tag OR ID > 0);",
        "DELETE FROM ORDERS WHERE NOT TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE TAG <> :run_tag;",
        "DELETE FROM ORDERS WHERE TAG != :run_tag;",
        "DELETE FROM ORDERS WHERE ID < :run_start;",
        "DELETE FROM ORDERS WHERE ID <= :run_start;",
        "DELETE FROM ORDERS WHERE ID >= :run_start - 99999999999;",
        "DELETE FROM ORDERS WHERE ID >= :run_start * 0;",
        "DELETE FROM ORDERS WHERE ID >= 0;",
        "DELETE FROM ORDERS WHERE ID = ID;",
        "DELETE FROM ORDERS WHERE TAG = ':run_tag';",
        "DELETE FROM ORDERS WHERE TAG = : run_tag;",
        "DELETE FROM ORDERS WHERE TAG = :1;",
        "DELETE FROM ORDERS WHERE EVILPKG.F(1) = 1 AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE ID IN (SELECT ID FROM USERS) AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE ID IN (SELECT ID FROM ITEMS, USERS) AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE ID IN (SELECT ID FROM ITEMS JOIN USERS ON 1=1) AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE ID IN (SELECT ID FROM (SELECT ID FROM USERS)) AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE ID IN (select id from users) AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE ID IN (SELECT ID FROM ITEMS@L) AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE ID IN (SELECT ID FROM ITEMS FOR UPDATE) AND TAG = :run_tag;",
        "DELETE FROM SYS.ORDERS WHERE TAG = :run_tag;",
        "DELETE FROM ORDERS@L WHERE TAG = :run_tag;",
        'DELETE FROM "ORDERS" WHERE TAG = :run_tag;',
        "DELETE FROM ORDERS WHERE TAG = &x;",
        "DELETE FROM ORDERS WHERE NAME = q'[x AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE TAG = :run_tag;\n/\nDROP TABLE ORDERS;\n/",
        "DELETE FROM ORDERS WHERE TAG = :run_tag; TRUNCATE TABLE ORDERS;",
        "DELETE FROM ORDERS WHERE TAG = :run_tag АND 1=1;",
        "DELETE FROM ORDERS WHERE TAG = :run_tag； DROP TABLE ORDERS;",
        "DELETE FROM ORDERS WHERE TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE TA​G = :run_tag;",
        "DELETE FROM ORDERS WHERE TAG = :run_tag﻿ OR 1=1;",
        "DELETE FROM ORDERS PARTITION (p1) WHERE TAG = :run_tag;",
        "DELETE FROM ORDERS AS OF TIMESTAMP SYSDATE WHERE TAG = :run_tag;",
        "",
        "   ;  ; ",
        "-- so comentario\n",
    ],
)
def test_gate_refuses_smuggling_forms(sql: str) -> None:
    assert _refused(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM ORDERS WHERE NAME = q'[x' OR 1=1 --]' AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE NAME = 'a;b' AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE NAME = 'a OR 1=1' AND TAG = :run_tag;",
        "DELETE FROM ORDERS WHERE TAG = :run_tag /*+ OR 1=1 */;",
        "delete from orders where tag = :run_tag;",
    ],
)
def test_gate_keeps_hostile_text_inside_literals_and_comments_out_of_the_sql(sql: str) -> None:
    script = parse_cleanup_script(sql.encode("utf-8"), POLICY)

    approved = script.statements[0].sql
    assert approved.count("OR 1=1") == sql.count("OR 1=1") - (1 if "/*+" in sql else 0)
    assert "/*" not in approved
