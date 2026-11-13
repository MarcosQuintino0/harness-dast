"""Verificação da condição `WHERE` de um comando de limpeza (parte do portão `cleanup_gate`).

Recebe as fichas depois do `WHERE` e garante: nada proibido, só tabelas permitidas, só funções
conhecidas, só variáveis do contrato, nenhuma comparação de constantes e ao menos uma condição
de amarração à execução (veja `cleanup_gate` para o conjunto de regras). Este módulo é puro.
"""

from harness_dast.domain.cleanup_sql import Token, TokenKind
from harness_dast.domain.errors import ConfigError


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


_FORBIDDEN = {
    word: f"a palavra {word} não é aceita no WHERE"
    for word in _words(
        "DROP TRUNCATE ALTER CREATE GRANT REVOKE MERGE INSERT UPDATE DELETE EXECUTE EXEC IMMEDIATE "
        "BEGIN DECLARE COMMIT ROLLBACK SAVEPOINT CALL LOCK INTO FOR RETURNING PURGE FLASHBACK "
        "TRUE FALSE"
    )
}
_FORBIDDEN_PREFIXES = ("DBMS_", "UTL_")
_SAFE_FUNCTIONS = _words(
    "UPPER LOWER TRUNC ROUND CEIL FLOOR ABS MOD NVL NULLIF COALESCE GREATEST LEAST TO_DATE "
    "TO_TIMESTAMP TO_CHAR TO_NUMBER SUBSTR INSTR LENGTH TRIM LTRIM RTRIM REPLACE ADD_MONTHS "
    "CAST"
)
_BEFORE_PAREN = _words(
    "IN EXISTS AND OR NOT ANY ALL SOME ON LIKE UNION MINUS INTERSECT FROM JOIN WHERE SELECT "
    "HAVING BY THEN ELSE WHEN CASE"
)
_NOT_ALIAS = _words(
    "WHERE JOIN INNER LEFT RIGHT FULL CROSS NATURAL OUTER ON USING GROUP ORDER UNION MINUS "
    "INTERSECT CONNECT START HAVING AND OR FOR"
)
_NOT_COLUMN = _words("NOT EXISTS ANY ALL SOME NULL AND OR IN LIKE BETWEEN")
_COMPARISONS = frozenset({"=", "<>", "!=", "^=", "<", ">", "<=", ">="})
_ANCHOR_OPERATORS = frozenset({"=", ">=", ">"})
_VALUE_KINDS = frozenset({TokenKind.BIND, TokenKind.STRING, TokenKind.NUMBER})


def read_qualified_name(tokens: list[Token], at: int) -> tuple[str, int] | None:
    """Lê `NOME` ou `ESQUEMA.NOME` em `at`.

    Returns:
        (nome em maiúsculas, posição seguinte), ou `None` se não há nome ali.
    """
    if at >= len(tokens) or tokens[at].kind is not TokenKind.WORD:
        return None
    name = tokens[at].upper
    if at + 2 < len(tokens) and tokens[at + 1].is_op(".") and tokens[at + 2].kind is TokenKind.WORD:
        return f"{name}.{tokens[at + 2].upper}", at + 3
    return name, at + 1


def _reject_forbidden(word: str) -> None:
    reason = _FORBIDDEN.get(word)
    if reason is None and word.startswith(_FORBIDDEN_PREFIXES):
        reason = f"o pacote {word} não é aceito no WHERE"
    if reason is not None:
        raise ConfigError(f"{reason}.")


class _Walker:
    """Percorre o WHERE uma vez, conferindo palavras, tabelas, chamadas e variáveis."""

    def __init__(
        self, tokens: list[Token], allowed_tables: frozenset[str], binds_allowed: frozenset[str]
    ) -> None:
        self._tokens = tokens
        self._tables = allowed_tables
        self._binds_allowed = binds_allowed
        self._depth = 0
        self._select_depths: set[int] = set()
        self._binds: dict[str, None] = {}

    def run(self) -> tuple[str, ...]:
        at = 0
        while at < len(self._tokens):
            at = self._step(at)
        if self._depth != 0:
            raise ConfigError("parênteses desbalanceados.")
        last = self._tokens[-1]
        if last.kind is TokenKind.OP and not last.is_op(")"):
            raise ConfigError("o comando termina em um operador (barra '/' solta?).")
        return tuple(self._binds)

    def _step(self, at: int) -> int:
        token = self._tokens[at]
        if token.kind is TokenKind.WORD:
            return self._word(at)
        if token.kind is TokenKind.BIND:
            self._bind(token)
        elif token.kind is TokenKind.OP:
            self._paren(token)
        return at + 1

    def _word(self, at: int) -> int:
        word = self._tokens[at].upper
        _reject_forbidden(word)
        if word == "SELECT":
            if at == 0 or not self._tokens[at - 1].is_op("("):
                raise ConfigError("SELECT só é aceito dentro de parênteses (subconsulta).")
            self._select_depths.add(self._depth)
        elif word == "FROM":
            if self._depth not in self._select_depths:
                raise ConfigError("FROM só é aceito dentro de uma subconsulta SELECT.")
            return self._table_refs(at + 1, several=True)
        elif word == "JOIN":
            return self._table_refs(at + 1, several=False)
        else:
            self._check_call(at, word)
        return at + 1

    def _check_call(self, at: int, word: str) -> None:
        opens = at + 1 < len(self._tokens) and self._tokens[at + 1].is_op("(")
        if not opens or word in _BEFORE_PAREN:
            return
        if at > 0 and self._tokens[at - 1].is_op("."):
            raise ConfigError(f"chamada de função de pacote ou esquema ({word}) não é aceita.")
        if word not in _SAFE_FUNCTIONS:
            raise ConfigError(
                f"a função {word} não está na lista de funções aceitas "
                "(uma função de usuário poderia gravar ou confirmar dados)."
            )

    def _table_refs(self, at: int, *, several: bool) -> int:
        while True:
            named = read_qualified_name(self._tokens, at)
            if named is None:
                raise ConfigError("esperado o nome de uma tabela (subconsulta não é aceita aqui).")
            table, at = named
            if table not in self._tables and table != "DUAL":
                raise ConfigError(
                    f"a tabela {table} da subconsulta não está em cleanup.allowed_tables."
                )
            if at < len(self._tokens) and self._is_alias(self._tokens[at]):
                at += 1
            if not (several and at < len(self._tokens) and self._tokens[at].is_op(",")):
                return at
            at += 1

    @staticmethod
    def _is_alias(token: Token) -> bool:
        if token.kind is not TokenKind.WORD or token.upper in _NOT_ALIAS:
            return False
        _reject_forbidden(token.upper)
        return True

    def _bind(self, token: Token) -> None:
        name = token.text[1:].lower()
        if name not in self._binds_allowed:
            shown = ", ".join(f":{n}" for n in sorted(self._binds_allowed))
            raise ConfigError(
                f"a variável de ligação :{name} não faz parte do contrato (permitidas: {shown})."
            )
        self._binds.setdefault(name)

    def _paren(self, token: Token) -> None:
        if token.is_op("("):
            self._depth += 1
        elif token.is_op(")"):
            self._depth -= 1
            if self._depth < 0:
                raise ConfigError("parênteses desbalanceados.")
            self._select_depths = {d for d in self._select_depths if d <= self._depth}


def _check_constants(tokens: list[Token]) -> None:
    """Recusa condição sempre verdadeira detectável pela forma (`1 = 1`, `X = X`)."""
    for left, operator, right in zip(tokens, tokens[1:], tokens[2:], strict=False):
        if operator.kind is not TokenKind.OP or operator.text not in _COMPARISONS:
            continue
        literals = {TokenKind.NUMBER, TokenKind.STRING}
        if left.kind in literals and right.kind in literals:
            raise ConfigError("comparação entre constantes (como 1 = 1) não delimita nada.")
        same = left.kind is right.kind and left.upper == right.upper
        if same and left.kind in {TokenKind.WORD, TokenKind.BIND}:
            raise ConfigError("o mesmo valor dos dois lados de uma comparação não delimita nada.")


def _closing_of_first(tokens: list[Token]) -> int:
    depth = 0
    for position, token in enumerate(tokens):
        if token.is_op("("):
            depth += 1
        elif token.is_op(")"):
            depth -= 1
            if depth == 0:
                return position
    return -1


def _unwrap(tokens: list[Token]) -> list[Token]:
    while len(tokens) > 2 and tokens[0].is_op("(") and _closing_of_first(tokens) == len(tokens) - 1:
        tokens = tokens[1:-1]
    return tokens


def _split_conjuncts(tokens: list[Token]) -> list[list[Token]]:
    """Divide pelo `AND` do nível de cima (o `AND` de um `BETWEEN` fica de fora)."""
    parts: list[list[Token]] = [[]]
    depth = 0
    in_between = False
    for token in tokens:
        if token.is_op("("):
            depth += 1
        elif token.is_op(")"):
            depth -= 1
        elif depth == 0 and token.is_word("BETWEEN"):
            in_between = True
        elif depth == 0 and token.is_word("AND"):
            if in_between:
                in_between = False
            else:
                parts.append([])
                continue
        parts[-1].append(token)
    return parts


def _is_value_expression(tokens: list[Token]) -> bool:
    """`operando || operando ...` só com variáveis e constantes, e ao menos uma variável.

    Sem aritmética nem parênteses: `:run_start - 36500` alargaria a amarração sem que o portão
    pudesse perceber.
    """
    if not tokens or len(tokens) % 2 == 0:
        return False
    operands_ok = all(token.kind in _VALUE_KINDS for token in tokens[0::2])
    separators_ok = all(token.is_op("||") for token in tokens[1::2])
    return operands_ok and separators_ok and any(t.kind is TokenKind.BIND for t in tokens[0::2])


def _is_bind_list(tokens: list[Token]) -> bool:
    """`( :a , :b )` com ao menos uma variável e nada além de variáveis e vírgulas."""
    if len(tokens) < 3 or not tokens[0].is_op("(") or not tokens[-1].is_op(")"):
        return False
    inner = tokens[1:-1]
    binds_ok = all(token.kind is TokenKind.BIND for token in inner[0::2])
    commas_ok = all(token.is_op(",") for token in inner[1::2])
    return binds_ok and commas_ok and len(inner) % 2 == 1


def _is_anchor(conjunct: list[Token]) -> bool:
    named = read_qualified_name(conjunct, 0)
    if named is None:
        return False
    column, at = named
    if column in _NOT_COLUMN or column.split(".")[-1] in _NOT_COLUMN or at >= len(conjunct):
        return False
    operator, rest = conjunct[at], conjunct[at + 1 :]
    if operator.kind is TokenKind.OP and operator.text in _ANCHOR_OPERATORS:
        return _is_value_expression(rest)
    if operator.is_word("LIKE"):
        return _is_value_expression(rest)
    return operator.is_word("IN") and _is_bind_list(rest)


def _has_top_level_or(tokens: list[Token]) -> bool:
    depth = 0
    for token in tokens:
        if token.is_op("("):
            depth += 1
        elif token.is_op(")"):
            depth -= 1
        elif depth == 0 and token.is_word("OR"):
            return True
    return False


def _require_anchor(tokens: list[Token]) -> None:
    # `A AND B OR C` é `(A AND B) OR C`: com OR no nível de cima, nenhuma condição amarra o todo.
    unwrapped = _unwrap(tokens)
    conjuncts = _split_conjuncts(unwrapped)
    if _has_top_level_or(unwrapped) or not any(_is_anchor(conjunct) for conjunct in conjuncts):
        raise ConfigError(
            "o WHERE não tem uma condição de amarração à execução no nível de cima, ligada por "
            "AND (por exemplo CREATED_AT >= :run_start, CREATED_BY IN (:account_1, ...) ou "
            "RUN_TAG = :run_tag), sem OR, NOT nem subconsulta."
        )


def check_where(
    body: list[Token], allowed_tables: frozenset[str], binds_allowed: frozenset[str]
) -> tuple[str, ...]:
    """Confere a condição de um `DELETE`.

    Args:
        body: Fichas depois da palavra `WHERE`, sem o `;`.
        allowed_tables: Tabelas permitidas (maiúsculas).
        binds_allowed: Nomes de variáveis do contrato (minúsculos).

    Returns:
        Os nomes (minúsculos) das variáveis de ligação usadas, sem repetição.

    Raises:
        ConfigError: A condição viola alguma regra do portão.
    """
    used = _Walker(body, allowed_tables, binds_allowed).run()
    _check_constants(body)
    _require_anchor(body)
    return used
