"""Registro de auditoria: formato das linhas de `audit.jsonl`.

Cada requisição que a CLI envia (ou tenta enviar) ao alvo gera DUAS linhas com o mesmo `seq`:

1. `phase: "decision"`, gravada ANTES do envio, com a decisão do `ScopeGuard` (`allowed` ou
   `denied`). Uma requisição negada só tem esta linha: nada foi enviado.
2. `phase: "result"`, gravada depois, com o status HTTP (ou o erro de transporte) e a duração.
   Uma decisão `allowed` sem linha de resultado indica interrupção durante o envio.

O arquivo só recebe acréscimos. Nunca entram cabeçalhos, corpo, valores de consulta, token,
senha nem cookie: da consulta ficam só os NOMES dos parâmetros. Este módulo é puro.
"""

from datetime import datetime
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.urlnorm import default_port

AuditPhase = Literal["decision", "result"]
AuditDecision = Literal["allowed", "denied"]


class AuditEntry(ApiModel):
    """Uma linha de `audit.jsonl`.

    Attributes:
        seq: Número da requisição na execução (1, 2, ...); decisão e resultado o compartilham.
        phase: `decision` ou `result`.
        timestamp: Instante da gravação (ISO 8601, UTC).
        method: Método HTTP.
        scheme: `http` ou `https`.
        host: Host da URL.
        port: Porta efetiva.
        path: Caminho da URL, sem consulta.
        query_names: Nomes dos parâmetros de consulta (nunca os valores).
        account: Apelido da conta que enviou, ou `None`.
        operation_id: Operação de origem (`auth.login` e `auth.csrf` para o próprio harness).
        route: `zap` (pelo proxy do ZAP) ou `auth` (login e token CSRF).
        decision: Na fase `decision`, `allowed` ou `denied`.
        reason: Na recusa, a mensagem do `ScopeGuard` (sem caminho nem consulta).
        status: Na fase `result`, o código HTTP; `None` se houve falha de transporte.
        error: Na fase `result`, o código do erro de transporte (`TARGET_TIMEOUT`...).
        duration_ms: Na fase `result`, a duração em milissegundos.
    """

    seq: int
    phase: AuditPhase
    timestamp: str
    method: str
    scheme: str
    host: str
    port: int
    path: str
    query_names: tuple[str, ...] = ()
    account: str | None = None
    operation_id: str
    route: str
    decision: AuditDecision | None = None
    reason: str | None = None
    status: int | None = None
    error: str | None = None
    duration_ms: int | None = None


def _base(seq: int, phase: AuditPhase, now: datetime, request: HttpRequest) -> dict[str, object]:
    parts = urlsplit(request.url)
    scheme = parts.scheme.lower()
    try:
        port = parts.port or default_port(scheme)
    except ValueError:
        port = 0
    return {
        "seq": seq,
        "phase": phase,
        "timestamp": now.isoformat(),
        "method": request.method,
        "scheme": scheme,
        "host": parts.hostname or "",
        "port": port,
        "path": parts.path,
        "query_names": tuple(name for name, _ in parse_qsl(parts.query, keep_blank_values=True)),
        "account": request.account,
        "operation_id": request.operation_id,
        "route": request.route,
    }


def decision_entry(
    seq: int, now: datetime, request: HttpRequest, *, reason: str | None = None
) -> AuditEntry:
    """Linha de decisão: `allowed` com `reason=None`; `denied` com o motivo da recusa."""
    decision: AuditDecision = "allowed" if reason is None else "denied"
    return AuditEntry.model_validate(
        {**_base(seq, "decision", now, request), "decision": decision, "reason": reason}
    )


def result_entry(
    seq: int,
    now: datetime,
    request: HttpRequest,
    *,
    status: int | None,
    error: str | None,
    duration_ms: int,
) -> AuditEntry:
    """Linha de resultado de uma requisição enviada."""
    return AuditEntry.model_validate(
        {
            **_base(seq, "result", now, request),
            "status": status,
            "error": error,
            "duration_ms": duration_ms,
        }
    )
