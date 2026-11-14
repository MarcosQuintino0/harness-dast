"""Trilha de auditoria: uma linha JSON por decisão, sem cabeçalhos, corpos nem valores de consulta.

O que garante: o registro só contém método, esquema, host, porta, caminho normalizado, NOMES
dos parâmetros de consulta, decisão, motivo, status, bytes e duração. O que não faz: não
decide nada e não sabe de mitmproxy.
"""

import json
from collections.abc import Callable
from typing import Literal, TextIO
from urllib.parse import parse_qsl

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.urlnorm import MAX_URL_LENGTH, normalize_request

_MAX_NAMES = 50
_MAX_NAME_TEXT = 120
# O caminho é guardado inteiro até o tamanho máximo de URL que o guarda aceita (2048): toda URL
# liberada cabe, então a linha basta para reproduzir a decisão. Acima disso a URL é recusada e
# o caminho é cortado (com marca), o que mantém a linha limitada.
_MAX_PATH_TEXT = MAX_URL_LENGTH
_TRUNCATED_MARK = "...[cortado]"


class AuditRecord(BaseModel):
    """Uma decisão do proxy.

    Attributes:
        ts: Instante em que o pedido foi liberado (ou recusado), ISO 8601 UTC com ms.
        run_id: Identificador da execução.
        method: Método como veio.
        scheme: `http` ou `https`.
        host: Host de destino.
        port: Porta de destino.
        path: Caminho normalizado (decodificado, sem consulta); se a URL for malformada, o
            caminho cru escapado e truncado.
        query_params: Só os nomes dos parâmetros de consulta.
        decision: `allow` ou `deny`.
        reason: Código de motivo estável (para recusa por forma, o agrupador `malformed_request`).
        detail: Código granular da recusa por forma (por exemplo `path_encoded_slash`) ou a
            marca de leitura fora de `allow` no modo amplo. Só aparece na linha quando existe.
        status: Status HTTP devolvido ao cliente, se houve.
        bytes: Tamanho do corpo da resposta, se conhecido.
        duration_ms: Duração total no proxy.
        waited_ms: Tempo na fila da taxa.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ts: str
    run_id: str
    method: str
    scheme: str
    host: str
    port: int
    path: str
    query_params: tuple[str, ...]
    decision: Literal["allow", "deny"]
    reason: str
    detail: str | None = None
    status: int | None = None
    bytes: int | None = None
    duration_ms: int | None = None
    waited_ms: int = 0


def _clip(text: str, limit: int) -> str:
    escaped = ascii(text)[1:-1]
    if len(escaped) <= limit:
        return escaped
    return escaped[: limit - len(_TRUNCATED_MARK)] + _TRUNCATED_MARK


def describe_target(method: str, url: str, raw_path: str, raw_query: str) -> tuple[str, list[str]]:
    """Devolve (caminho para o registro, nomes dos parâmetros de consulta).

    Args:
        method: Método da requisição.
        url: URL absoluta, usada para normalizar o caminho.
        raw_path: Caminho cru, usado só se a URL não normalizar.
        raw_query: Consulta crua; os valores são descartados aqui.
    """
    try:
        path = normalize_request(method, url).path
    except ScopeViolation:
        path = _clip(raw_path, _MAX_PATH_TEXT)
    names = [
        _clip(name, _MAX_NAME_TEXT) for name, _ in parse_qsl(raw_query, keep_blank_values=True)
    ]
    return path, names[:_MAX_NAMES]


class AuditLog:
    """Grava os registros em arquivo (que sobrevive ao `down`) e na saída padrão."""

    def __init__(self, *, file: TextIO, stdout: TextIO, on_failure: Callable[[], None]) -> None:
        """Cria o gravador.

        Args:
            file: Arquivo aberto para acréscimo, em texto UTF-8.
            stdout: Fluxo da saída padrão do contêiner.
            on_failure: Chamado se a gravação falhar, para o proxy travar a execução.
        """
        self._file = file
        self._stdout = stdout
        self._on_failure = on_failure

    def write(self, record: AuditRecord) -> None:
        """Grava uma linha; falha de E/S aciona `on_failure` em vez de ser engolida."""
        data = record.model_dump()
        if data["detail"] is None:
            del data["detail"]  # linhas sem detalhe ficam idênticas às de antes do campo existir
        line = json.dumps(data, ensure_ascii=True, separators=(",", ":")) + "\n"
        try:
            self._file.write(line)
            self._file.flush()
            self._stdout.write(line)
            self._stdout.flush()
        except OSError:
            self._on_failure()
