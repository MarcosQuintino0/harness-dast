"""Identificador do recurso criado por um `POST` e o alvo do `GET` que o lê (ADR 0040).

A atribuição em massa num `POST` precisa ler o recurso que acabou de ser criado. O identificador
vem só do que o servidor devolveu a ESTA requisição: primeiro o cabeçalho `Location` (caminho
relativo ou URL da própria `base_url`, do mesmo recurso que o `GET` provado pelo `probe`), depois
o campo de primeiro nível do corpo da resposta com o nome do marcador do `GET` ou `id`. Nada é
adivinhado, e identificador com `/`, `..`, espaço ou mais de 64 caracteres é recusado. O alvo
montado ainda passa pelo `ScopeGuard` como qualquer pedido. Este módulo é puro.
"""

import json
import re
from typing import Final

from pydantic import ValidationError

from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz_config import normalize_field_name
from harness_dast.domain.probe_exchange import ExchangeRecord

_IDENTIFIER: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")
_MAX_LOCATION: Final = 2000


def _segments(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def _relative(location: str, base_url: str) -> str | None:
    """Caminho do `Location` relativo à `base_url`, ou `None` se aponta para outro lugar."""
    if len(location) > _MAX_LOCATION or any(ch in location for ch in "\\ \t\r\n#"):
        return None
    prefix = base_url.rstrip("/")
    if location.startswith(("http://", "https://")):
        if not location.startswith(prefix + "/"):
            return None
        location = location[len(prefix) :]
    if not location.startswith("/") or location.startswith("//"):
        return None
    return location.split("?", 1)[0]


def _from_location(location: str | None, reader: ExchangeRecord, base_url: str) -> str | None:
    if location is None:
        return None
    path = _relative(location, base_url)
    if path is None:
        return None
    wanted = _segments(reader.target.split("?", 1)[0])
    found = _segments(path)
    if len(found) != len(wanted) or found[:-1] != wanted[:-1]:
        return None
    return found[-1] if _IDENTIFIER.fullmatch(found[-1]) else None


def _marker_name(reader: ExchangeRecord) -> str:
    last = _segments(reader.path)[-1]
    return normalize_field_name(last.strip("{}"))


def _from_body(body: bytes, reader: ExchangeRecord) -> str | None:
    try:
        parsed: JsonValue = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(parsed, dict):
        return None
    names = {_marker_name(reader), "id"}
    for key, value in parsed.items():
        if normalize_field_name(key) not in names or isinstance(value, bool):
            continue
        if isinstance(value, str | int) and _IDENTIFIER.fullmatch(str(value)):
            return str(value)
    return None


def created_identifier(
    *, location: str | None, body: bytes, reader: ExchangeRecord, base_url: str
) -> str | None:
    """Identificador do recurso criado, ou `None` se o servidor não o devolveu de forma segura.

    Args:
        location: Cabeçalho `Location` da resposta do `POST`, se houve.
        body: Corpo da resposta do `POST`.
        reader: `GET` provado do mesmo recurso (com um marcador final no caminho).
        base_url: URL base do ambiente.
    """
    return _from_location(location, reader, base_url) or _from_body(body, reader)


def created_read_exchange(reader: ExchangeRecord, identifier: str) -> ExchangeRecord | None:
    """`GET` do recurso criado: o do `probe` com o identificador novo no lugar do último segmento.

    Devolve `None` se o alvo montado não é um caminho relativo simples. A consulta do `GET` do
    `probe` é descartada.
    """
    if not _IDENTIFIER.fullmatch(identifier):
        return None
    prefix = _segments(reader.target.split("?", 1)[0])[:-1]
    target = "/" + "/".join([*prefix, identifier])
    try:
        return ExchangeRecord.model_validate({**reader.model_dump(), "target": target})
    except ValidationError:
        return None
