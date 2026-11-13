"""Analisador léxico conservador do SQL de limpeza.

Transforma o texto do script em uma lista de fichas (palavras, textos, números, variáveis
de ligação, operadores e `;`) sem comentários. É a primeira metade do portão de segurança
da limpeza (a segunda é `cleanup_gate`).

Postura: o que este módulo não entende com certeza é recusado, nunca adivinhado. Em especial:

- texto e comentário que não fecham, `q'[...]'` sem fim e controle (exceto tabulação e fim de
  linha) viram erro, para que ninguém esconda um segundo comando onde o leitor e o Oracle
  discordariam sobre onde um comentário termina;
- o retorno de carro isolado (CR sem LF) é recusado, porque `--` termina em LF para o
  Oracle e a divergência esconderia código;
- fora de texto e comentário só existe ASCII: letras parecidas de outro alfabeto não passam;
- `&` em qualquer lugar (inclusive em texto) e `@` fora de texto são recusados, assim como
  `"identificadores entre aspas"` e `:=`, `::` ou `:` solto.

Este módulo é puro: sem I/O e sem relógio.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from harness_dast.domain.errors import ConfigError

_LEX_HINT = (
    "Reescreva o comando de limpeza sem esse trecho; o script aceita só DELETE FROM ... WHERE "
    "com variáveis de ligação (veja docs/operations/cleanup.md)."
)


class TokenKind(StrEnum):
    """Classe de uma ficha do SQL."""

    WORD = "word"
    STRING = "string"
    NUMBER = "number"
    BIND = "bind"
    OP = "op"
    SEMI = "semi"


@dataclass(frozen=True, slots=True)
class Token:
    """Uma ficha do SQL, sem comentários.

    Attributes:
        kind: Classe da ficha.
        text: Texto exatamente como escrito no script.
        line: Linha (a partir de 1) onde a ficha começa.
    """

    kind: TokenKind
    text: str
    line: int

    @property
    def upper(self) -> str:
        """Texto em maiúsculas (palavras do SQL não diferenciam caixa)."""
        return self.text.upper()

    def is_op(self, symbol: str) -> bool:
        """Diz se é o operador ou a pontuação `symbol`."""
        return self.kind is TokenKind.OP and self.text == symbol

    def is_word(self, word: str) -> bool:
        """Diz se é a palavra `word` (sem diferenciar caixa)."""
        return self.kind is TokenKind.WORD and self.upper == word


class LexError(ConfigError):
    """O script tem um trecho que o analisador léxico não aceita."""


_WHITESPACE = re.compile(r"[ \t\n\r]+")
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING = re.compile(r"'(?:[^']|'')*'")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_$#]*")
_NUMBER = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_BIND = re.compile(r":(?:[A-Za-z][A-Za-z0-9_]*|[0-9]+)")
_OPERATOR = re.compile(r"<=|>=|<>|!=|\^=|\|\||[=<>+\-*/%(),.]")
_Q_OPEN = re.compile(r"(?:[nN]?[qQ])'")
_Q_CLOSERS = {"[": "]", "{": "}", "(": ")", "<": ">"}
_ALLOWED_CONTROL = frozenset("\t\n\r")
_SPECIAL_CHARS = {
    "@": "link de banco de dados (@) não é aceito",
    "&": "substituição de variável (&) não é aceita",
    '"': "identificador entre aspas duplas não é aceito",
    ":": "':' só é aceito em variável de ligação (:nome); ':=' é PL/SQL",
}

type _Reader = Callable[[str, int], tuple[TokenKind | None, int] | None]
"""Leitor de uma ficha na posição dada: devolve (classe, fim) ou `None` se não casa.

A classe `None` marca o que deve ser descartado (espaço e comentário)."""


def _fail(message: str, line: int) -> LexError:
    return LexError(f"{message} (linha {line}).", hint=_LEX_HINT)


def _read_trivia(text: str, pos: int) -> tuple[TokenKind | None, int] | None:
    for pattern in (_WHITESPACE, _LINE_COMMENT):
        match = pattern.match(text, pos)
        if match:
            return None, match.end()
    return None


def _read_block_comment(text: str, pos: int) -> tuple[TokenKind | None, int] | None:
    if not text.startswith("/*", pos):
        return None
    match = _BLOCK_COMMENT.match(text, pos)
    if match is None:
        raise LexError("Comentário /* */ sem fechamento.", hint=_LEX_HINT)
    return None, match.end()


def _read_q_literal(text: str, pos: int) -> tuple[TokenKind | None, int] | None:
    opening = _Q_OPEN.match(text, pos)
    if opening is None:
        return None
    start = opening.end()
    if start >= len(text) or text[start] in " \t\r\n'":
        raise LexError("Literal q'...' com delimitador inválido.", hint=_LEX_HINT)
    closing = _Q_CLOSERS.get(text[start], text[start]) + "'"
    end = text.find(closing, start + 1)
    if end < 0:
        raise LexError("Literal q'...' sem fechamento.", hint=_LEX_HINT)
    return TokenKind.STRING, end + len(closing)


def _read_string(text: str, pos: int) -> tuple[TokenKind | None, int] | None:
    if text[pos] != "'":
        return None
    match = _STRING.match(text, pos)
    if match is None:
        raise LexError("Texto entre aspas simples sem fechamento.", hint=_LEX_HINT)
    return TokenKind.STRING, match.end()


def _read_regex(
    pattern: re.Pattern[str], kind: TokenKind
) -> Callable[[str, int], tuple[TokenKind | None, int] | None]:
    def read(text: str, pos: int) -> tuple[TokenKind | None, int] | None:
        match = pattern.match(text, pos)
        return (kind, match.end()) if match else None

    return read


def _read_semicolon(text: str, pos: int) -> tuple[TokenKind | None, int] | None:
    return (TokenKind.SEMI, pos + 1) if text[pos] == ";" else None


# A ordem importa: `q'` antes de palavra, bind antes de operador, número antes de `.`.
_READERS: tuple[_Reader, ...] = (
    _read_trivia,
    _read_block_comment,
    _read_q_literal,
    _read_string,
    _read_regex(_WORD, TokenKind.WORD),
    _read_regex(_BIND, TokenKind.BIND),
    _read_regex(_NUMBER, TokenKind.NUMBER),
    _read_regex(_OPERATOR, TokenKind.OP),
    _read_semicolon,
)


def _check_characters(text: str) -> None:
    """Recusa controle, retorno de carro isolado e `&`, em qualquer lugar do texto."""
    for number, line in enumerate(text.split("\n"), start=1):
        body = line[:-1] if line.endswith("\r") else line
        if "\r" in body:
            raise _fail("Retorno de carro isolado (\\r) não é aceito", number)
        if "&" in line:
            raise _fail(_SPECIAL_CHARS["&"], number)
    for char in text:
        if unicodedata.category(char) == "Cc" and char not in _ALLOWED_CONTROL:
            raise LexError("O script contém caractere de controle.", hint=_LEX_HINT)


def _unexpected(text: str, pos: int, line: int) -> LexError:
    char = text[pos]
    if char in _SPECIAL_CHARS:
        return _fail(_SPECIAL_CHARS[char], line)
    if not char.isascii():
        return _fail("Caractere não ASCII fora de texto ou comentário", line)
    return _fail("Caractere inesperado", line)


def tokenize(text: str) -> tuple[Token, ...]:
    """Divide o script em fichas, sem espaços nem comentários.

    Args:
        text: Conteúdo do script (já decodificado).

    Returns:
        As fichas, na ordem em que aparecem.

    Raises:
        LexError: Texto ou comentário sem fechamento, caractere fora do conjunto aceito,
            controle, `&`, `@`, aspas duplas ou `:` fora de variável de ligação.
    """
    _check_characters(text)
    tokens: list[Token] = []
    pos = 0
    line = 1
    while pos < len(text):
        for reader in _READERS:
            found = reader(text, pos)
            if found is not None:
                break
        else:
            raise _unexpected(text, pos, line)
        kind, end = found
        if kind is not None:
            tokens.append(Token(kind, text[pos:end], line))
        line += text.count("\n", pos, end)
        pos = end
    return tuple(tokens)
