"""Mensagens HTTP do histórico do ZAP e a requisição aprendida que delas sai.

O `probe` envia pelo proxy do ZAP, que guarda cada requisição como mensagem. O `scan` precisa
do método, da URL e do corpo EXATOS de cada uma (o ZAP exige o `postData` idêntico ao
aprendido para achar o nó). Esses valores vivem só em memória: nenhum modelo gravado em
disco os contém. Este módulo é puro.
"""

import re
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

_REQUEST_LINE: Final = re.compile(r"^([A-Z]{3,10}) (\S+) HTTP/\d(?:\.\d)?$")
_STATUS_LINE: Final = re.compile(r"^HTTP/\d(?:\.\d)? (\d{3})(?:\s|$)")
_ABSOLUTE: Final = re.compile(r"^https?://", re.IGNORECASE)


class ZapMessage(BaseModel):
    """Mensagem do histórico do ZAP como a API a devolve.

    Attributes:
        id: Identificador da mensagem no ZAP.
        type: Tipo (`1` = proxy, o que o `probe` gera); `None` quando a API não informa.
        request_header: Cabeçalho da requisição, com a linha de requisição.
        request_body: Corpo da requisição.
        response_header: Cabeçalho da resposta, com a linha de status.
        response_body: Corpo da resposta.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    type: str | None = None
    request_header: str = Field(default="", repr=False)
    request_body: str = Field(default="", repr=False)
    response_header: str = Field(default="", repr=False)
    response_body: str = Field(default="", repr=False)


class LearnedRequest(BaseModel):
    """Requisição que o ZAP aprendeu (uma por operação enviada pelo `probe`).

    Attributes:
        message_id: Identificador da mensagem no ZAP.
        method: Método HTTP.
        url: URL absoluta com consulta (somente em memória; não é gravada).
        body: Corpo ou `None` (somente em memória; não é gravado).
        status: Código HTTP da resposta, ou `None`.
    """

    model_config = ConfigDict(frozen=True)

    message_id: int
    method: str
    url: str = Field(repr=False)
    body: str | None = Field(default=None, repr=False)
    status: int | None = None


def _host_header(header: str) -> str | None:
    for line in header.splitlines()[1:]:
        name, _, value = line.partition(":")
        if name.strip().lower() == "host" and value.strip():
            return value.strip()
    return None


def parse_learned_request(message: ZapMessage, base_scheme: str) -> LearnedRequest | None:
    """Extrai método, URL e corpo da mensagem; `None` se a linha de requisição é ilegível.

    Args:
        message: Mensagem do histórico.
        base_scheme: Esquema do ambiente (`http` ou `https`), usado quando o ZAP registrou a
            requisição em forma de origem (`GET /x`) e a URL precisa ser montada com `Host`.
    """
    lines = message.request_header.splitlines()
    match = _REQUEST_LINE.match(lines[0].strip()) if lines else None
    if match is None:
        return None
    method, target = match.group(1), match.group(2)
    if _ABSOLUTE.match(target):
        url = target
    else:
        host = _host_header(message.request_header)
        if host is None or not target.startswith("/"):
            return None
        url = f"{base_scheme}://{host}{target}"
    status_match = _STATUS_LINE.match(message.response_header.strip())
    return LearnedRequest(
        message_id=message.id,
        method=method,
        url=url,
        body=message.request_body or None,
        status=int(status_match.group(1)) if status_match else None,
    )
