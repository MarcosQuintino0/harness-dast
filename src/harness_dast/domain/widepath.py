"""Leituras de um caminho no modo amplo do proxy de escopo. Módulo puro.

Para que serve: no modo amplo o proxy libera formas de caminho que o modo estrito recusa
(`;`, ponto ou espaço final, `%2f`, dupla codificação, `//`). Em troca, antes de liberar,
confere contra `scope.deny_paths` TODAS as leituras que um servidor poderia fazer do caminho.

O que garante:
- `literal_segments` devolve a leitura literal (decodificada uma vez, separada pelas barras
  cruas), que é a única que vale para PERMITIR;
- `interpretations` devolve um conjunto FINITO de leituras alternativas, fechado sob as
  transformações abaixo (aplicadas em qualquer ordem e repetidas até não haver novidade), com
  teto de custo; passar do teto levanta `ScopeViolation` (recusa), nunca libera.

O que não faz: não decide escopo, não compara com padrões e não conhece método nem host.

Transformações (cada uma é o que algum servidor ou camada faz antes de rotear):
decodificar uma vez (`%2f` vira separador), barra invertida como separador, remover `;param`
por segmento, aparar ponto e espaço, resolver `.` e `..`, colapsar `//`, remover o sufixo de
formato do último segmento (`.json`) e normalização Unicode NFKC (a largura total vira ASCII).
Diferença
de maiúsculas e minúsculas é tratada na comparação (`pathpattern.fold_segment`).

Limitações conhecidas (não cobertas, como no modo estrito): `::$DATA` e nomes 8.3 do IIS;
decodificação em Latin-1 de bytes inválidos em UTF-8 (o modo amplo recusa UTF-8 inválido).
"""

import re
import unicodedata
from collections.abc import Callable
from urllib.parse import unquote

from harness_dast.domain.host import violation
from harness_dast.domain.scope_reason import ScopeReason

MAX_READINGS = 256
"""Teto de leituras distintas por requisição. Cada leitura custa uma passada sobre um caminho de
no máximo 2048 caracteres por transformação (8); com 256 leituras o pior caso fica na casa de
milissegundos, compatível com milhares de decisões por minuto. Acima disso o caminho é
recusado (`path_too_many_readings`): só aparece com dupla codificação absurda."""

_FORMAT_SUFFIX = re.compile(r"\.[A-Za-z0-9_\-]{1,16}$")


def literal_segments(raw_path: str) -> tuple[str, ...]:
    """Leitura literal: cada segmento cru (barras cruas) decodificado UMA vez.

    `%2f` e `%5c` ficam dentro do segmento (não separam); `;`, ponto/espaço final, `%` solto e
    segmento vazio (`//`) são aceitos. Uma barra final é ignorada.

    Raises:
        ScopeViolation: Segmento `.` ou `..` (cru ou codificado uma vez), UTF-8 inválido, ou
            caractere de controle/espaço invisível depois de decodificar.
    """
    if raw_path in {"", "/"}:
        return ()
    parts = raw_path[1:].split("/")
    if parts[-1] == "":
        parts.pop()
    return tuple(_decode_literal(part) for part in parts)


def _decode_literal(part: str) -> str:
    try:
        decoded = unquote(part, errors="strict")
    except UnicodeDecodeError:
        raise violation(
            "Caminho com percent-encoding que não é UTF-8 válido.",
            reason=ScopeReason.PATH_INVALID_UTF8,
        ) from None
    if decoded in {".", ".."}:
        raise violation(
            "Caminho com segmento '.' ou '..' (travessia) foi recusado.",
            reason=ScopeReason.PATH_DOT_SEGMENT,
        )
    for char in decoded:
        if char != " " and (char.isspace() or unicodedata.category(char).startswith("C")):
            raise violation(
                "Caminho com caractere de controle ou espaço invisível foi recusado.",
                reason=ScopeReason.PATH_CONTROL_CHAR,
            )
    return decoded


def interpretations(raw_path: str) -> tuple[tuple[str, ...], ...]:
    """Leituras alternativas do caminho, em segmentos, para conferir contra `deny_paths`.

    Parte do caminho cru e aplica, em qualquer ordem e até não haver leitura nova, as
    transformações descritas no módulo. Inclui o próprio caminho cru (sem decodificar).

    Returns:
        Tupla de leituras distintas, em ordem estável.

    Raises:
        ScopeViolation: Se passar de `MAX_READINGS` leituras (recusa por segurança).
    """
    start = raw_path or "/"
    seen: dict[str, None] = {start: None}
    frontier = [start]
    while frontier:
        following: list[str] = []
        for path in frontier:
            for transform in _TRANSFORMS:
                result = transform(path)
                if result in seen:
                    continue
                if len(seen) >= MAX_READINGS:
                    raise violation(
                        "O caminho admite leituras demais (dupla codificação em excesso) e "
                        "foi recusado.",
                        reason=ScopeReason.PATH_TOO_MANY_READINGS,
                    )
                seen[result] = None
                following.append(result)
        frontier = following
    return tuple(dict.fromkeys(_to_segments(path) for path in seen))


def _to_segments(path: str) -> tuple[str, ...]:
    parts = path.split("/")[1:]
    if parts and parts[-1] == "":
        parts.pop()
    return tuple(parts)


def _decode_once(path: str) -> str:
    # `errors="replace"`: aqui só importa o que SOBRA para comparar com a negação; UTF-8
    # inválido já foi recusado na leitura literal.
    return unquote(path, errors="replace")


def _backslash_as_slash(path: str) -> str:
    return path.replace("\\", "/")


def _split(path: str) -> tuple[str, list[str]]:
    head, _, rest = path.partition("/")
    return head, rest.split("/") if "/" in path else []


def _map_segments(path: str, change: Callable[[str], str]) -> str:
    head, segments = _split(path)
    return "/".join([head, *(change(segment) for segment in segments)])


def _strip_params(path: str) -> str:
    return _map_segments(path, lambda segment: segment.split(";", 1)[0])


def _trim_segment(segment: str) -> str:
    segment = segment.lstrip(" ")
    bare = segment.rstrip(" ")
    if bare in {".", ".."}:
        return bare  # '..' aparado seguiria sendo travessia; não vira segmento vazio
    return segment.rstrip(". ")


def _trim(path: str) -> str:
    return _map_segments(path, _trim_segment)


def _resolve_dots(path: str) -> str:
    head, segments = _split(path)
    kept: list[str] = []
    for segment in segments:
        if segment == ".":
            continue
        if segment == "..":
            if kept:
                kept.pop()
            continue
        kept.append(segment)
    return "/".join([head, *kept])


def _collapse_empty(path: str) -> str:
    head, segments = _split(path)
    return "/".join([head, *(segment for segment in segments if segment != "")])


def _drop_format_suffix(path: str) -> str:
    head, segments = _split(path)
    index = len(segments) - 1
    while index >= 0 and segments[index] == "":
        index -= 1
    if index >= 0:
        stripped = _FORMAT_SUFFIX.sub("", segments[index])
        if stripped:
            segments[index] = stripped
    return "/".join([head, *segments])


def _nfkc(path: str) -> str:
    return unicodedata.normalize("NFKC", path)


_TRANSFORMS: tuple[Callable[[str], str], ...] = (
    _decode_once,
    _backslash_as_slash,
    _strip_params,
    _trim,
    _resolve_dots,
    _collapse_empty,
    _drop_format_suffix,
    _nfkc,
)
