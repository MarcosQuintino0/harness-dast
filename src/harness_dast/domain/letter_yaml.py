"""Escritor de YAML determinístico para o `target.yml` gerado da carta (ADR 0036).

Não usa `yaml.dump`: a saída precisa ser idêntica byte a byte para a mesma carta (ordem de
chaves fixada por quem monta o mapa, textos sempre entre aspas, sem dependência de versão do
PyYAML). Aceita só o que o perfil gerado usa: mapa de texto, lista, texto, inteiro, decimal,
booleano e data. Este módulo é puro.
"""

import json
from collections.abc import Mapping
from datetime import date
from typing import Final

_INDENT: Final = 2
_MAX_BMP: Final = 0xFFFF


def render_yaml(data: Mapping[str, object]) -> str:
    """Escreve `data` como YAML em blocos, na ordem das chaves, terminando em quebra de linha.

    Raises:
        TypeError: Valor de tipo não suportado (erro de programação do chamador).
    """
    return "\n".join(_dict_lines(data, 0)) + "\n"


def _dict_lines(mapping: Mapping[str, object], indent: int) -> list[str]:
    lines: list[str] = []
    pad = " " * indent
    for key, value in mapping.items():
        if isinstance(value, Mapping) and value:
            lines.append(f"{pad}{key}:")
            lines.extend(_dict_lines(value, indent + _INDENT))
        elif isinstance(value, list) and value:
            lines.append(f"{pad}{key}:")
            lines.extend(_list_lines(value, indent + _INDENT))
        else:
            lines.append(f"{pad}{key}: {_scalar(value)}")
    return lines


def _list_lines(items: list[object], indent: int) -> list[str]:
    lines: list[str] = []
    pad = " " * indent
    for item in items:
        if isinstance(item, Mapping) and item:
            inner = _dict_lines(item, indent + _INDENT)
            lines.append(f"{pad}- {inner[0][indent + _INDENT :]}")
            lines.extend(inner[1:])
        else:
            lines.append(f"{pad}- {_scalar(item)}")
    return lines


def _scalar(value: object) -> str:
    # bool antes de int: bool é subclasse de int.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, list) and not value:
        return "[]"
    if isinstance(value, Mapping) and not value:
        return "{}"
    raise TypeError(f"tipo não suportado no YAML gerado: {type(value).__name__}")


def _quote(text: str) -> str:
    # json.dumps cuida de aspas e barras; o que não é imprimível (inclusive separadores de linha
    # Unicode, que o YAML trata como quebra) vira escape, para o texto nunca mudar de linha.
    quoted = json.dumps(text, ensure_ascii=False)
    return "".join(
        char
        if char.isprintable()
        else (f"\\u{ord(char):04x}" if ord(char) <= _MAX_BMP else f"\\U{ord(char):08x}")
        for char in quoted
    )
