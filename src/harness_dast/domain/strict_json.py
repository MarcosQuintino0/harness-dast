"""Decodificação de JSON sem ambiguidades, sem I/O e sem expor valores inválidos."""

import json

from harness_dast.domain.errors import ConfigError


def parse_strict_json(data: str | bytes) -> object:
    """Decodifica JSON e recusa chaves repetidas e constantes não finitas.

    Raises:
        ConfigError: Conteúdo malformado, ambíguo ou profundo demais. A mensagem
            não contém valores da entrada. Não valida o schema do documento.
    """
    try:
        result: object = json.loads(
            data, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant
        )
    except (UnicodeError, ValueError, RecursionError):
        raise ConfigError("JSON inválido ou ambíguo.", hint="Confira o arquivo.") from None
    return result


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("chave duplicada")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("constante JSON inválida")
