"""Propriedade: todo script que o portão aceita só tem DELETE ... WHERE em tabelas permitidas.

O oráculo é independente do portão: uma máquina de estados caractere a caractere (sem regex e
sem reutilizar o analisador léxico) que separa os comandos por `;` fora de texto e comentário e
confere a forma de cada um.
"""

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.errors import NoSuchExample

from harness_dast.domain.cleanup_gate import CleanupPolicy, parse_cleanup_script
from harness_dast.domain.errors import ConfigError

ALLOWED = frozenset({"PEDIDO", "ITEM"})
POLICY = CleanupPolicy(allowed_tables=ALLOWED, account_count=2)
DANGEROUS = frozenset(
    {
        "DROP",
        "TRUNCATE",
        "ALTER",
        "CREATE",
        "GRANT",
        "REVOKE",
        "MERGE",
        "INSERT",
        "UPDATE",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "BEGIN",
        "DECLARE",
        "EXECUTE",
        "EXEC",
        "IMMEDIATE",
        "CALL",
    }
)
VALID = [
    "DELETE FROM PEDIDO WHERE CREATED_AT >= :run_start AND CREATED_BY IN (:account_1);",
    "DELETE FROM ITEM I WHERE I.RUN_ID = :run_id;",
    "delete from pedido where run_tag = :run_tag and status = 'A';",
    "DELETE FROM ITEM WHERE CREATED_AT >= :run_start AND PEDIDO_ID IN (SELECT ID FROM PEDIDO);",
]
HOSTILE = [
    "DROP TABLE PEDIDO;",
    "DELETE FROM PEDIDO;",
    "DELETE FROM OUTRA WHERE CREATED_AT >= :run_start;",
    "DELETE FROM PEDIDO WHERE 1 = 1;",
    "TRUNCATE TABLE ITEM;",
    "BEGIN NULL; END;",
    "COMMIT;",
    "EXECUTE IMMEDIATE 'x';",
    "UPDATE PEDIDO SET X = 1 WHERE RUN_ID = :run_id;",
    "'",
    "--",
    "/*",
    "*/",
    "q'[",
    "]'",
    ";",
    " ; DROP TABLE X; ",
    "/* ; DROP TABLE X; */",
    "-- ; DROP TABLE X;\n",
    "'; DROP TABLE X; --'",
    "\n/\n",
    "DROP",
    "\uff24ROP TABLE X;",
    "@x",
    "&x",
    ":foo",
    "\r",
]
NEWLINE = chr(10)
PIECES = st.sampled_from(VALID + HOSTILE)


@st.composite
def scripts(draw: st.DrawFn) -> str:
    """Um script válido com até quatro peças (válidas ou hostis) inseridas em lugares aleatórios."""
    text = "\n".join(draw(st.lists(st.sampled_from(VALID), min_size=1, max_size=3)))
    for _ in range(draw(st.integers(min_value=0, max_value=4))):
        position = draw(st.integers(min_value=0, max_value=len(text)))
        text = text[:position] + draw(PIECES) + text[position:]
    return text


def oracle(text: str) -> list[list[str]] | None:
    """Palavras (maiúsculas) de cada comando em código; `None` se não fecha ou não é ASCII."""
    statements: list[list[str]] = [[]]
    i = 0
    while i < len(text):
        char = text[i]
        if char == ";":
            statements.append([])
            i += 1
            continue
        if not char.isascii():
            return None
        word_end = _word_end(text, i)
        if word_end > i:
            statements[-1].append(text[i:word_end].upper())
            i = word_end
            continue
        i = _skip_inert(text, i)
        if i < 0:
            return None
    return [words for words in statements if words]


def _word_end(text: str, i: int) -> int:
    """Fim da palavra que começa em `i`, ou `i` se ali não começa uma palavra."""
    if _starts_q_literal(text, i) or not (text[i].isalpha() or text[i] == "_"):
        return i
    j = i
    while j < len(text) and text[j].isascii() and (text[j].isalnum() or text[j] in "_$#"):
        j += 1
    return j


def _skip_inert(text: str, i: int) -> int:
    """Pula comentário, texto ou um caractere qualquer; devolve -1 se algo não fecha."""
    if text.startswith("--", i):
        end = text.find(NEWLINE, i)
        return len(text) if end < 0 else end
    if text.startswith("/*", i):
        end = text.find("*/", i + 2)
        return -1 if end < 0 else end + 2
    if text[i] == "'" or _starts_q_literal(text, i):
        return _skip_string(text, i)
    return i + 1


def _starts_q_literal(text: str, i: int) -> bool:
    before_ok = i == 0 or not (text[i - 1].isalnum() or text[i - 1] in "_$#")
    prefix = text[i : i + 3].lower()
    return before_ok and (prefix[:2] == "q'" or prefix == "nq'")


def _skip_string(text: str, i: int) -> int:
    """Posição depois do texto que começa em `i`, ou -1 se não fecha."""
    if text[i] == "'":
        j = i + 1
        while j < len(text):
            if text[j] == "'":
                if text.startswith("''", j):
                    j += 2
                    continue
                return j + 1
            j += 1
        return -1
    start = text.index("'", i) + 1
    if start >= len(text):
        return -1
    opener = text[start]
    closer = {"[": "]", "{": "}", "(": ")", "<": ">"}.get(opener, opener)
    end = text.find(closer + "'", start + 1)
    return -1 if end < 0 else end + 2


def accepted(text: str) -> bool:
    try:
        parse_cleanup_script(text.encode("utf-8"), POLICY)
    except ConfigError:
        return False
    return True


@settings(max_examples=600, deadline=None)
@given(scripts())
def test_every_accepted_script_is_only_delete_where_on_allowed_tables(text: str) -> None:
    if not accepted(text):
        return

    statements = oracle(text)

    assert statements is not None
    assert statements, "script aceito sem comandos"
    for words in statements:
        assert words[:2] == ["DELETE", "FROM"]
        assert words[2] in ALLOWED
        assert "WHERE" in words
        assert not DANGEROUS & set(words)
    assert len(statements) == len(parse_cleanup_script(text.encode("utf-8"), POLICY).statements)


def test_generator_reaches_accepted_scripts_so_the_property_is_not_vacuous() -> None:
    from hypothesis import find

    try:
        found = find(scripts(), accepted, settings=settings(max_examples=2000, deadline=None))
    except NoSuchExample:  # pragma: no cover - só ocorre se o gerador quebrar
        found = ""

    assert accepted(found)
