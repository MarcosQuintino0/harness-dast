r"""Subconjunto SEGURO de expressões regulares: análise, verificação e síntese.

Por que existe: o campo `pattern` de um OpenAPI vem de documento não confiável. Executá-lo
com `re` contra valores gerados abriria a porta para backtracking catastrófico (ReDoS), e
gerar um texto que case com uma regex arbitrária não é determinístico. Aqui só se aceita
uma gramática pequena, sem grupos nem alternância, que casa em tempo polinomial:

    padrão   := ['^'] átomo* ['$']
    átomo    := (literal | '.' | '[' classe ']' | '\\' escape) quantificador?
    quantif. := '?' | '*' | '+' | '{n}' | '{n,}' | '{n,m}'    (n, m <= 256)
    escape   := d D w W s S, ou um caractere de pontuação escapado

Qualquer outra construção (grupos, `|`, âncoras no meio, `\\b`, referências) faz
`parse_pattern` devolver `None`: o padrão é "não suportado" e quem precisa gerar um valor
deve pedir uma regra explícita ao agente. Sem `^`/`$` o padrão casa "contém", como no JSON
Schema. Este módulo é puro e não usa `re`.
"""

from dataclasses import dataclass

_MAX_COUNT = 256
_MAX_CLASS_SPAN = 256
_MAX_TEXT = 2048
_MAX_TOKENS = 200
_SPECIAL = frozenset("\\^$.|?*+()[]{}")
_DIGITS = frozenset("0123456789")
_WORD = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
_SPACE = frozenset(" \t\n\r\f\v")
_PREFERRED = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PRINTABLE = "".join(chr(code) for code in range(33, 127))
_CLASS_ESCAPES = {
    "d": (_DIGITS, False),
    "D": (_DIGITS, True),
    "w": (_WORD, False),
    "W": (_WORD, True),
    "s": (_SPACE, False),
    "S": (_SPACE, True),
}


@dataclass(frozen=True)
class CharClass:
    """Conjunto de caracteres: os `members`, ou todos MENOS eles quando `negated`."""

    members: frozenset[str]
    negated: bool = False

    def contains(self, char: str) -> bool:
        """Diz se o caractere pertence ao conjunto."""
        return (char in self.members) != self.negated

    def representative(self) -> str:
        """Escolhe, de forma determinística, um caractere do conjunto."""
        for char in _PREFERRED + _PRINTABLE:
            if self.contains(char):
                return char
        return min(self.members)


@dataclass(frozen=True)
class Token:
    """Um átomo com repetição: `chars` repetido de `low` a `high` vezes (`None` = sem teto)."""

    chars: CharClass
    low: int
    high: int | None


@dataclass(frozen=True)
class ParsedPattern:
    """Padrão analisado: a lista de átomos e se está ancorado no início e no fim."""

    tokens: tuple[Token, ...]
    anchored_start: bool
    anchored_end: bool


_ANY = CharClass(frozenset(), negated=True)


def parse_pattern(pattern: str) -> ParsedPattern | None:
    """Analisa o padrão; devolve `None` se ele sai da gramática suportada.

    Args:
        pattern: Texto do `pattern` do esquema.

    Returns:
        O padrão analisado, ou `None` se não for suportado. Nunca levanta exceção.
    """
    anchored_start = pattern.startswith("^")
    body = pattern[1:] if anchored_start else pattern
    anchored_end = body.endswith("$") and not body.endswith("\\$")
    body = body[:-1] if anchored_end else body
    tokens: list[Token] = []
    position = 0
    while position < len(body):
        parsed = _parse_atom(body, position)
        if parsed is None or len(tokens) >= _MAX_TOKENS:
            return None
        chars, position = parsed
        quantified = _parse_quantifier(body, position)
        if quantified is None:
            return None
        low, high, position = quantified
        tokens.append(Token(chars, low, high))
    return ParsedPattern(tuple(tokens), anchored_start, anchored_end)


def _parse_atom(body: str, position: int) -> tuple[CharClass, int] | None:
    char = body[position]
    if char == "[":
        return _parse_class(body, position + 1)
    if char == "\\":
        return _parse_escape(body, position + 1)
    if char == ".":
        return _ANY, position + 1
    if char in _SPECIAL:
        return None
    return CharClass(frozenset(char)), position + 1


def _parse_escape(body: str, position: int) -> tuple[CharClass, int] | None:
    if position >= len(body):
        return None
    char = body[position]
    if char in _CLASS_ESCAPES:
        members, negated = _CLASS_ESCAPES[char]
        return CharClass(members, negated), position + 1
    if char.isascii() and char.isalnum():
        return None
    return CharClass(frozenset(char)), position + 1


def _parse_class(body: str, position: int) -> tuple[CharClass, int] | None:
    negated = body.startswith("^", position)
    position += 1 if negated else 0
    members: set[str] = set()
    first = True
    while position < len(body):
        char = body[position]
        if char == "]" and not first:
            return CharClass(frozenset(members), negated), position + 1
        first = False
        item = _parse_class_item(body, position)
        if item is None:
            return None
        added, position = item
        members |= added
        if len(members) > _MAX_CLASS_SPAN:
            return None
    return None


def _parse_class_item(body: str, position: int) -> tuple[set[str], int] | None:
    start = _class_char(body, position)
    if start is None:
        return None
    first, position = start
    if len(first) != 1 or body[position : position + 1] != "-" or body[position + 1 :][:1] == "]":
        return set(first), position
    end = _class_char(body, position + 1)
    if end is None or len(end[0]) != 1:
        return None
    last, position = end
    low, high = ord(next(iter(first))), ord(next(iter(last)))
    if high < low or high - low >= _MAX_CLASS_SPAN:
        return None
    return {chr(code) for code in range(low, high + 1)}, position


def _class_char(body: str, position: int) -> tuple[frozenset[str], int] | None:
    if position >= len(body):
        return None
    char = body[position]
    if char == "\\":
        escaped = _parse_escape(body, position + 1)
        if escaped is None or escaped[0].negated:
            return None
        return escaped[0].members, escaped[1]
    if char == "[":
        return None
    return frozenset(char), position + 1


def _parse_quantifier(body: str, position: int) -> tuple[int, int | None, int] | None:
    if position >= len(body) or body[position] not in "?*+{":
        return 1, 1, position
    char = body[position]
    simple = {"?": (0, 1), "*": (0, None), "+": (1, None)}
    if char in simple:
        low, high = simple[char]
        return low, high, position + 1
    return _parse_braces(body, position + 1)


def _is_count(text: str) -> bool:
    return text.isascii() and text.isdigit()


def _parse_braces(body: str, position: int) -> tuple[int, int | None, int] | None:
    close = body.find("}", position)
    if close == -1:
        return None
    parts = body[position:close].split(",")
    if len(parts) > 2 or not _is_count(parts[0]):
        return None
    low = int(parts[0])
    high: int | None = low
    if len(parts) == 2:
        if parts[1] and not _is_count(parts[1]):
            return None
        high = int(parts[1]) if parts[1] else None
    if low > _MAX_COUNT or (high is not None and (high > _MAX_COUNT or high < low)):
        return None
    return low, high, close + 1


def matches(parsed: ParsedPattern, text: str) -> bool:
    """Diz se `text` satisfaz o padrão (casamento completo se ancorado, "contém" se não).

    Tempo polinomial no tamanho do texto e do padrão, sem backtracking exponencial. Textos
    maiores que 2048 caracteres nunca casam (nenhum valor gerado chega perto disso).
    """
    if len(text) > _MAX_TEXT:
        return False
    tokens = list(parsed.tokens)
    if not parsed.anchored_start:
        tokens.insert(0, Token(_ANY, 0, None))
    if not parsed.anchored_end:
        tokens.append(Token(_ANY, 0, None))
    positions = {0}
    for token in tokens:
        positions = _advance(token, text, positions)
        if not positions:
            return False
    return len(text) in positions


def _advance(token: Token, text: str, positions: set[int]) -> set[int]:
    reached: set[int] = set()
    for start in positions:
        end = start
        while True:
            count = end - start
            if count >= token.low:
                reached.add(end)
            if (token.high is not None and count >= token.high) or end >= len(text):
                break
            if not token.chars.contains(text[end]):
                break
            end += 1
    return reached


def synthesize(parsed: ParsedPattern, min_length: int, max_length: int | None) -> str | None:
    """Monta um texto determinístico que casa o padrão e respeita o tamanho pedido.

    Usa o mínimo de repetições de cada átomo e, se faltar tamanho, alonga os átomos que
    admitem mais, da esquerda para a direita.

    Args:
        parsed: Padrão suportado.
        min_length: Tamanho mínimo exigido pelo esquema.
        max_length: Tamanho máximo exigido, ou `None`.

    Returns:
        O texto, ou `None` se o padrão e o tamanho não puderem ser satisfeitos juntos.
    """
    counts = [token.low for token in parsed.tokens]
    missing = min_length - sum(counts)
    for index, token in enumerate(parsed.tokens):
        if missing <= 0:
            break
        room = missing if token.high is None else min(token.high - token.low, missing)
        counts[index] += room
        missing -= room
    if missing > 0 or (max_length is not None and sum(counts) > max_length):
        return None
    return "".join(
        token.chars.representative() * count
        for token, count in zip(parsed.tokens, counts, strict=True)
    )
