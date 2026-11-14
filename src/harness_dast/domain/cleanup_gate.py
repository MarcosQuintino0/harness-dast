"""Portão de segurança do SQL de limpeza: só `DELETE FROM <tabela> WHERE ...` amarrado à execução.

IMPORTANTE: este portão é defesa em profundidade, NÃO uma prova. Um analisador sintático
conservador reduz o dano de um script errado, mas não substitui o que de fato protege o
ambiente: o usuário de banco da limpeza, que só deve ter `DELETE` (e `SELECT`) nas tabelas de
teste. Veja `docs/operations/cleanup.md` para o que o portão garante e o que não garante.

O que ele aceita, por comando (separados por `;`):

    DELETE FROM <tabela> [apelido] WHERE <condição>

- `<tabela>` (e toda tabela de subconsulta `FROM`/`JOIN`) está em `allowed_tables` (ou é `DUAL`);
- a condição tem, no nível de cima, ao menos uma condição de AMARRAÇÃO ligada pelo `AND`:
  `coluna = | >= | > <expressão só de ligações e constantes>`, `coluna LIKE <idem>` ou
  `coluna IN (:a, :b, ...)`, sem `OR`, `NOT` nem subconsulta dentro dela. Assim nenhuma
  combinação de `OR` e de condições extras consegue alargar o `DELETE` para além do que as
  variáveis da execução (`:run_start`, `:run_id`, `:run_tag`, `:account_N`) delimitam;
- só variáveis de ligação do contrato (`cleanup_binds`); nenhuma concatenação de valor;
- só funções conhecidas e sem efeito colateral (função de usuário poderia gravar ou confirmar).

Recusa (com `ConfigError`): `DELETE` sem `WHERE`, `WHERE` sem amarração ou com constantes
comparadas entre si (`1 = 1`), `TRUNCATE`, `DROP`, `ALTER`, `CREATE`, `GRANT`, `MERGE`,
`INSERT`, `UPDATE` (não suportado na V1), blocos PL/SQL, `EXECUTE IMMEDIATE`, `COMMIT`,
`ROLLBACK` e `SAVEPOINT` (a CLI é dona da transação), link de banco (`@`), `&variável`,
tabela fora da lista e variável fora do contrato.

Limites conhecidos (documentados no guia do operador): o portão não sabe o que as colunas
significam (uma amarração `ID >= :run_start` passaria); não vê gatilhos, visões nem
sinônimos que apontem para outras tabelas; não conhece a semântica de dados do produto.

Este módulo é puro.
"""

import hashlib
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.cleanup_binds import allowed_bind_names
from harness_dast.domain.cleanup_sql import Token, TokenKind, tokenize
from harness_dast.domain.cleanup_where import check_where, read_qualified_name
from harness_dast.domain.errors import ConfigError

MAX_SCRIPT_BYTES = 64 * 1024
MAX_STATEMENTS = 100
_HINT = (
    "O script de limpeza aceita só 'DELETE FROM <tabela> WHERE <coluna> >= :run_start AND ...' "
    "com variáveis do contrato (veja docs/operations/cleanup.md)."
)
_REASON_BY_FIRST_WORD = {
    "TRUNCATE": "TRUNCATE não é aceito",
    "DROP": "DROP não é aceito",
    "ALTER": "ALTER não é aceito",
    "CREATE": "CREATE não é aceito",
    "GRANT": "GRANT não é aceito",
    "REVOKE": "REVOKE não é aceito",
    "MERGE": "MERGE não é aceito",
    "INSERT": "INSERT não é aceito",
    "UPDATE": "UPDATE não é aceito na V1 (só DELETE)",
    "SELECT": "SELECT solto não é aceito (só como subconsulta dentro do WHERE)",
    "COMMIT": "COMMIT não é aceito: quem controla a transação é a CLI",
    "ROLLBACK": "ROLLBACK não é aceito: quem controla a transação é a CLI",
    "SAVEPOINT": "SAVEPOINT não é aceito: quem controla a transação é a CLI",
    "BEGIN": "bloco PL/SQL (BEGIN) não é aceito",
    "DECLARE": "bloco PL/SQL (DECLARE) não é aceito",
    "EXECUTE": "EXECUTE não é aceito",
    "EXEC": "EXEC não é aceito",
    "CALL": "CALL não é aceito",
    "LOCK": "LOCK não é aceito",
    "SET": "SET não é aceito (a CLI configura a sessão)",
}
_RESERVED_ALIASES = frozenset(_REASON_BY_FIRST_WORD) | {
    "AND",
    "AS",
    "BY",
    "DELETE",
    "FROM",
    "GROUP",
    "IN",
    "INTO",
    "NOT",
    "OR",
    "ORDER",
    "RETURNING",
    "UNION",
    "USING",
    "VALUES",
}


class CleanupStatement(BaseModel):
    """Um comando já aprovado pelo portão.

    Attributes:
        index: Posição do comando no script, a partir de 1.
        table: Tabela alvo do `DELETE`, em maiúsculas (`ESQUEMA.TABELA` se qualificada).
        sql: Texto a executar: as fichas aprovadas unidas por espaço, SEM comentários e sem
            o `;` final. É exatamente o que o portão analisou.
        binds: Nomes (minúsculos) das variáveis de ligação usadas pelo comando.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    table: str
    sql: str
    binds: tuple[str, ...]


class CleanupScript(BaseModel):
    """Script aprovado.

    Attributes:
        sha256: SHA-256 (hex) dos bytes do arquivo.
        statements: Comandos, na ordem do arquivo.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str
    statements: tuple[CleanupStatement, ...]

    @property
    def tables(self) -> tuple[str, ...]:
        """Tabelas distintas, na ordem em que aparecem."""
        return tuple(dict.fromkeys(statement.table for statement in self.statements))


class CleanupPolicy(BaseModel):
    """O que o perfil autoriza ao script.

    Attributes:
        allowed_tables: Tabelas permitidas, em maiúsculas (`TABELA` ou `ESQUEMA.TABELA`).
        account_count: Quantas contas de login o perfil tem (define `:account_1..N`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed_tables: frozenset[str]
    account_count: int


@dataclass(frozen=True, slots=True)
class _Head:
    table: str
    where_at: int


def _fail(index: int, reason: str) -> ConfigError:
    return ConfigError(f"Comando {index} do script de limpeza recusado: {reason}.", hint=_HINT)


def _split_statements(tokens: tuple[Token, ...]) -> list[list[Token]]:
    statements: list[list[Token]] = [[]]
    for token in tokens:
        if token.kind is TokenKind.SEMI:
            statements.append([])
        else:
            statements[-1].append(token)
    return [statement for statement in statements if statement]


def _parse_head(index: int, tokens: list[Token], policy: CleanupPolicy) -> _Head:
    first = tokens[0]
    if first.kind is not TokenKind.WORD:
        raise _fail(
            index, "o comando não começa por DELETE (a barra '/' e símbolos soltos não valem)"
        )
    if first.upper != "DELETE":
        reason = _REASON_BY_FIRST_WORD.get(first.upper, "só DELETE FROM ... WHERE é aceito")
        raise _fail(index, reason)
    if len(tokens) < 3 or not tokens[1].is_word("FROM"):
        raise _fail(index, "esperado 'DELETE FROM <tabela>'")
    named = read_qualified_name(tokens, 2)
    if named is None:
        raise _fail(index, "esperado o nome da tabela depois de FROM")
    table, at = named
    if table not in policy.allowed_tables:
        raise _fail(
            index,
            f"a tabela {table} não está em cleanup.allowed_tables do perfil "
            "(inclua-a só se a pessoa dona do produto concordar)",
        )
    if at < len(tokens) and tokens[at].kind is TokenKind.WORD and not tokens[at].is_word("WHERE"):
        # Apelido da tabela. Palavra reservada nunca vale como apelido: falha fechada mesmo
        # quando o Oracle recusaria o comando ao executar.
        if tokens[at].upper in _RESERVED_ALIASES:
            raise _fail(index, f"{tokens[at].upper} não vale como apelido da tabela")
        at += 1
    if at >= len(tokens) or not tokens[at].is_word("WHERE"):
        raise _fail(index, "DELETE sem WHERE (ou WHERE escondido em comentário)")
    return _Head(table=table, where_at=at)


def _check_statement(
    index: int, tokens: list[Token], policy: CleanupPolicy, binds_allowed: frozenset[str]
) -> CleanupStatement:
    head = _parse_head(index, tokens, policy)
    body = tokens[head.where_at + 1 :]
    if not body:
        raise _fail(index, "WHERE vazio")
    try:
        used = check_where(body, policy.allowed_tables, binds_allowed)
    except ConfigError as error:
        raise _fail(index, error.message.rstrip(".")) from None
    return CleanupStatement(
        index=index,
        table=head.table,
        sql=" ".join(token.text for token in tokens),
        binds=used,
    )


def _decode(raw: bytes) -> str:
    if len(raw) > MAX_SCRIPT_BYTES:
        raise ConfigError(
            f"O script de limpeza passa de {MAX_SCRIPT_BYTES // 1024} KiB.",
            hint="Um script de limpeza legítimo é pequeno; confira se o arquivo é o correto.",
        )
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ConfigError(
            "O script de limpeza não está em UTF-8.", hint="Salve o arquivo como UTF-8."
        ) from None


def parse_cleanup_script(raw: bytes, policy: CleanupPolicy) -> CleanupScript:
    """Analisa o script e devolve os comandos aprovados, ou recusa o script inteiro.

    Args:
        raw: Bytes do arquivo (UTF-8, até `MAX_SCRIPT_BYTES`).
        policy: Tabelas permitidas e quantidade de contas.

    Returns:
        O script aprovado, com o SHA-256 dos bytes recebidos.

    Raises:
        ConfigError: Qualquer violação (veja o docstring do módulo). A mensagem cita o número
            do comando ou a linha, nunca valores de ligação.
    """
    tokens = tokenize(_decode(raw))
    statements = _split_statements(tokens)
    if not statements:
        raise ConfigError(
            "O script de limpeza não tem nenhum comando.",
            hint="Escreva ao menos um DELETE FROM ... WHERE ... terminado em ';'.",
        )
    if len(statements) > MAX_STATEMENTS:
        raise ConfigError(
            f"O script de limpeza tem mais de {MAX_STATEMENTS} comandos.",
            hint="Divida a limpeza ou revise o script.",
        )
    binds_allowed = allowed_bind_names(policy.account_count)
    approved = tuple(
        _check_statement(number, statement, policy, binds_allowed)
        for number, statement in enumerate(statements, start=1)
    )
    return CleanupScript(sha256=hashlib.sha256(raw).hexdigest(), statements=approved)
