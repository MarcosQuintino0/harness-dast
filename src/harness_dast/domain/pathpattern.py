"""Padrões de caminho do escopo: validação, casamento e cobertura.

Semântica dos padrões (contrato público, usada em `scope.allow[].paths` e `scope.deny_paths`):

- Um padrão começa com `/` e é dividido em segmentos por `/`. Uma barra final é ignorada.
- Segmento literal casa com um segmento do caminho, comparação exata (maiúsculas importam).
- `*` casa exatamente UM segmento qualquer (nunca vazio). `/api/*` casa `/api/a`,
  não casa `/api` nem `/api/a/b`.
- `**` casa ZERO ou mais segmentos. `/api/**` casa `/api`, `/api/a` e `/api/a/b/c`.
- Curinga parcial (`us*`, `*.json`) é inválido: só segmentos inteiros `*` ou `**`.
- `/` casa somente a raiz.
- Segmentos vazios (`//`), `.`, `..`, `%`, `;`, `?`, `#`, barra invertida e espaços são
  inválidos num padrão.

Este módulo é puro: não faz I/O.
"""

import unicodedata
from collections.abc import Callable

_MAX_PATTERN_LENGTH = 256
_FORBIDDEN_CHARS = frozenset("\\%;?# ")


def parse_pattern(raw: str) -> tuple[str, ...]:
    """Valida um padrão de caminho e devolve seus segmentos.

    Args:
        raw: Padrão como escrito no perfil, por exemplo `/api/**`.

    Returns:
        Tupla de segmentos (vazia para o padrão `/`, que casa só a raiz).

    Raises:
        ValueError: Se o padrão for ambíguo ou perigoso (não começa com `/`, tem segmento
            vazio, `.`/`..`, curinga parcial, caractere de controle etc.). A mensagem é em
            português e não repete o padrão inteiro.
    """
    if not raw:
        raise ValueError("padrão de caminho vazio")
    if len(raw) > _MAX_PATTERN_LENGTH:
        raise ValueError(f"padrão de caminho maior que {_MAX_PATTERN_LENGTH} caracteres")
    if not raw.startswith("/"):
        raise ValueError("padrão de caminho deve começar com '/'")
    _reject_forbidden_chars(raw)
    segments = raw[1:].split("/")
    if segments[-1] == "":
        segments.pop()
    return tuple(_validate_segment(segment) for segment in segments)


def _reject_forbidden_chars(raw: str) -> None:
    for char in raw:
        # Controle e formatação (inclui bidi e largura zero) permitiriam esconder o que o
        # padrão realmente cobre.
        if char in _FORBIDDEN_CHARS or unicodedata.category(char).startswith("C"):
            raise ValueError(
                "padrão de caminho contém caractere proibido "
                "(barra invertida, %, ;, ?, #, espaço ou controle)"
            )
        if char.isspace():
            raise ValueError("padrão de caminho contém espaço em branco")


def _validate_segment(segment: str) -> str:
    if segment == "":
        raise ValueError("padrão de caminho tem segmento vazio ('//')")
    if segment in {".", ".."}:
        raise ValueError("padrão de caminho não pode conter '.' nem '..'")
    if "*" in segment and segment not in {"*", "**"}:
        raise ValueError("curinga parcial não é permitido: use '*' ou '**' como segmento inteiro")
    return segment


def format_pattern(tokens: tuple[str, ...]) -> str:
    """Devolve a forma canônica (texto) de um padrão já analisado."""
    return "/" + "/".join(tokens)


def fold_segment(segment: str) -> str:
    """Forma de comparação sem diferença de caixa nem de composição Unicode.

    Usada só nas regras de NEGAÇÃO: um servidor pode tratar `/API/Conta` e `/api/conta`
    como o mesmo recurso, e a negação precisa cobrir todas as grafias possíveis.
    """
    return unicodedata.normalize("NFKC", segment).casefold()


def matches(pattern: tuple[str, ...], segments: tuple[str, ...], *, fold: bool = False) -> bool:
    """Diz se o caminho (já normalizado, em segmentos) casa com o padrão.

    Args:
        pattern: Segmentos devolvidos por `parse_pattern`.
        segments: Segmentos decodificados do caminho da requisição.
        fold: Se verdadeiro, ignora caixa e composição Unicode (regras de negação).

    Returns:
        `True` somente se o caminho inteiro casar. Nunca levanta; entrada vazia casa
        apenas com o padrão `/`.
    """
    normalize = fold_segment if fold else _identity
    wanted = tuple(normalize(token) if token not in {"*", "**"} else token for token in pattern)
    states = _closure({0}, wanted)
    for segment in segments:
        current = normalize(segment)
        following: set[int] = set()
        for position in states:
            if position == len(wanted):
                continue
            element = wanted[position]
            if element == "**":
                following.add(position)
            elif element in {"*", current}:
                following.add(position + 1)
        states = _closure(following, wanted)
    return len(wanted) in states


def _identity(segment: str) -> str:
    return segment


def _closure(states: set[int], pattern: tuple[str, ...]) -> set[int]:
    """Estende o conjunto de estados com os `**` que podem casar zero segmentos."""
    result = set(states)
    for position in sorted(states):
        cursor = position
        while cursor < len(pattern) and pattern[cursor] == "**":
            cursor += 1
            result.add(cursor)
    return result


def covers(wide: tuple[str, ...], narrow: tuple[str, ...]) -> bool:
    """Diz se TODO caminho que casa `narrow` também casa `wide`.

    A resposta é conservadora: `True` garante a inclusão; `False` pode ocorrer mesmo em
    alguns casos de inclusão real. Serve para garantir que uma sobrescrita só estreite o
    escopo. Comparação literal exata (maiúsculas importam).
    """
    memo: dict[tuple[int, int], bool] = {}

    def walk(i: int, j: int) -> bool:
        key = (i, j)
        if key not in memo:
            memo[key] = _covers_step(wide, narrow, i, j, walk)
        return memo[key]

    return walk(0, 0)


def _covers_step(
    wide: tuple[str, ...],
    narrow: tuple[str, ...],
    i: int,
    j: int,
    walk: Callable[[int, int], bool],
) -> bool:
    if i == len(wide):
        return j == len(narrow)
    if wide[i] == "**":
        # `**` pode casar zero segmentos ou absorver o próximo elemento do padrão estreito.
        return walk(i + 1, j) or (j < len(narrow) and walk(i, j + 1))
    if j == len(narrow) or narrow[j] == "**":
        return False
    if wide[i] == "*" or wide[i] == narrow[j]:
        return walk(i + 1, j + 1)
    return False
