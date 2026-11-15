"""Veredito da reação do servidor a um valor proibido, e a severidade proposta (ADR 0051).

A resposta esperada a um valor que o contrato proíbe é a rejeição (4xx). Aceitar (2xx) e 5xx são
falhas. Resposta que não permite concluir (a conta perdeu a permissão, o recurso sumiu, limite de
taxa, redirecionamento, sem resposta) é `inconclusive` e nunca conta como seguro nem como falha.
O corpo da resposta nunca é lido aqui: só o código. Este módulo é puro.
"""

from dataclasses import dataclass
from typing import Final, Literal

from harness_dast.domain.negative_values import CaseClass
from harness_dast.domain.zap_alert import Severity

Verdict = Literal["rejected", "accepted", "server_error", "inconclusive"]

_INCONCLUSIVE: Final[dict[int, str]] = {
    401: "unauthorized",
    403: "unauthorized",
    404: "not_found",
    410: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "rate_limited",
}
STOP_REASONS: Final = frozenset({"unauthorized", "not_found"})
"""Motivos em que os demais casos da operação não adiantam (a conta ou o recurso sumiu)."""
_REASON_TEXT: Final[dict[str, str]] = {
    "unauthorized": "a conta perdeu a permissão (401 ou 403)",
    "not_found": "o recurso não existe mais (404 ou 410)",
    "method_not_allowed": "o método não é aceito (405)",
    "conflict": "conflito (409)",
    "create_conflict": "conflito no cadastro (409), em geral valor único repetido",
    "rate_limited": "limite de taxa do alvo (429)",
    "redirect": "redirecionamento (3xx)",
    "no_response": "o alvo não respondeu",
    "unexpected_status": "código HTTP fora do esperado",
}
_REDIRECT_FLOOR: Final = 300
_CLIENT_FLOOR: Final = 400
_SERVER_FLOOR: Final = 500
_SERVER_CEILING: Final = 599
_OK_FLOOR: Final = 200


@dataclass(frozen=True)
class Reaction:
    """Veredito de uma resposta.

    Attributes:
        verdict: `rejected`, `accepted`, `server_error` ou `inconclusive`.
        reason: Motivo estável, só quando `inconclusive`.
    """

    verdict: Verdict
    reason: str | None = None


def reason_text(reason: str) -> str:
    """Frase curta em português para um motivo de `inconclusive`."""
    return _REASON_TEXT.get(reason, reason)


def judge(status: int | None, method: str) -> Reaction:
    """Veredito do código HTTP recebido.

    Args:
        status: Código HTTP, ou `None` se não houve resposta.
        method: Método do caso (um 409 em `POST` é `create_conflict`).
    """
    if status is None:
        return Reaction("inconclusive", "no_response")
    if status in _INCONCLUSIVE:
        reason = _INCONCLUSIVE[status]
        if status == 409 and method.upper() == "POST":
            reason = "create_conflict"
        return Reaction("inconclusive", reason)
    if _OK_FLOOR <= status < _REDIRECT_FLOOR:
        return Reaction("accepted")
    if _REDIRECT_FLOOR <= status < _CLIENT_FLOOR:
        return Reaction("inconclusive", "redirect")
    if _CLIENT_FLOOR <= status < _SERVER_FLOOR:
        return Reaction("rejected")
    if _SERVER_FLOOR <= status <= _SERVER_CEILING:
        return Reaction("server_error")
    return Reaction("inconclusive", "unexpected_status")


def proposed_severity(method: str, case_class: CaseClass, verdict: Verdict) -> Severity:
    """Severidade proposta (só `accepted` e `server_error` geram achado).

    Em `GET`, baixa nos dois casos. Em escrita, média, exceto aceitar `wrong_type` (coerção
    costuma ser legítima), que é baixa.
    """
    if method.upper() == "GET":
        return "low"
    if verdict == "accepted" and case_class == "wrong_type":
        return "low"
    return "medium"
