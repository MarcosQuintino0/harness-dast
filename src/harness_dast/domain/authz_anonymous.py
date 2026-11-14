"""Plano e decisões das verificações "pedido sem login" e "token adulterado" (ADR 0039).

O plano escolhe, entre os `GET` que o `probe` provou, as operações a repetir sem credencial
(`anonymous_access`) e com o token adulterado (`tampered_token`), e diz o que fica sem teste e
por quê. A severidade e a conclusão sobre as variantes de token saem daqui, em código: nem o
agente nem o adaptador decidem. Este módulo é puro e nunca vê o valor de um token.
"""

from collections.abc import Mapping, Sequence
from typing import Final, Literal

from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz_compare import Verdict
from harness_dast.domain.authz_config import AuthzCheck
from harness_dast.domain.authz_plan import Planned
from harness_dast.domain.authz_result import AuthzNotTested
from harness_dast.domain.authz_token import TamperVariant
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.zap_alert import Severity

AccessCheck = Literal["anonymous_access", "tampered_token"]
Conclusion = Literal["finding", "tested", "inconclusive"]

MAX_ANONYMOUS_OPERATIONS: Final = 200
MAX_TAMPERED_OPERATIONS: Final = 100
OPERATION_CAP: Final[Mapping[AccessCheck, int]] = {
    "anonymous_access": MAX_ANONYMOUS_OPERATIONS,
    "tampered_token": MAX_TAMPERED_OPERATIONS,
}
"""Teto de operações por execução; o excedente vai para `not_tested` (`budget_exhausted`)."""

CWE_TOKEN_NOT_VERIFIED: Final = 287
CWE_SIGNATURE_NOT_VERIFIED: Final = 347


def declared_anonymous(operation: Operation | None) -> bool:
    """Diz se o OpenAPI declara a operação como anônima (alguma alternativa sem esquema).

    Operação sem nenhuma declaração de `security` NÃO conta: ela é testada, com severidade menor.
    """
    return operation is not None and any(not item.schemes for item in operation.security)


def anonymous_severity(operation: Operation | None) -> Severity:
    """Alta se o OpenAPI exige autenticação na operação; média se não declara `security`."""
    return "high" if operation is not None and operation.requires_auth else "medium"


def tampered_cwe(variants: Sequence[TamperVariant]) -> int:
    """CWE-347 se alguma variante de JWT foi aceita; CWE-287 se só o texto embaralhado foi."""
    jwt_accepted = any(name != "scrambled" for name in variants)
    return CWE_SIGNATURE_NOT_VERIFIED if jwt_accepted else CWE_TOKEN_NOT_VERIFIED


def conclude_variants(results: Sequence[tuple[TamperVariant, Verdict]]) -> Conclusion:
    """Conclusão sobre as variantes enviadas.

    - `finding`: alguma variante recebeu 2xx com corpo equivalente à linha de base.
    - `inconclusive`: nenhuma foi aceita, mas alguma ficou sem resposta ou deu 5xx (ou nada
      foi enviado): não conta como seguro.
    - `tested`: todas foram recusadas (ou deram 2xx com corpo diferente).
    """
    if any(verdict == "allowed_equivalent" for _, verdict in results):
        return "finding"
    if not results or any(verdict in {"error", "baseline_failed"} for _, verdict in results):
        return "inconclusive"
    return "tested"


def accepted_variants(
    results: Sequence[tuple[TamperVariant, Verdict]],
) -> tuple[TamperVariant, ...]:
    """Nomes das variantes aceitas (2xx com corpo equivalente), na ordem enviada."""
    return tuple(name for name, verdict in results if verdict == "allowed_equivalent")


def _note(
    check: AuthzCheck, exchange: ExchangeRecord | None, reason: str, why: str
) -> AuthzNotTested:
    return AuthzNotTested(
        check=check,
        operation_id=exchange.operation_id if exchange else None,
        method=exchange.method if exchange else None,
        path=exchange.path if exchange else None,
        reason=reason,
        message=why,
    )


def _skip_reason(
    item: ExchangeRecord,
    operation: Operation | None,
    public: frozenset[str],
    infrastructure: frozenset[str],
) -> tuple[str, str] | None:
    if item.operation_id in public:
        return "public_operation", "Marcada como pública no perfil (authz.public_operations)."
    if declared_anonymous(operation):
        return (
            "declared_public",
            "O OpenAPI declara esta operação como anônima: responder sem login é o esperado.",
        )
    if item.path in infrastructure:
        return (
            "infrastructure_path",
            "Login, saúde e preparação existem para responder sem sessão: não são testados.",
        )
    return None


def plan_access(
    check: AccessCheck,
    exchanges: Sequence[ExchangeRecord],
    operations: Mapping[str, Operation],
    public: frozenset[str],
    infrastructure: frozenset[str],
) -> Planned[ExchangeRecord]:
    """Candidatas de `anonymous_access` ou `tampered_token`: um `GET` por `operation_id`.

    Args:
        check: Verificação (decide só o teto de operações e o rótulo das notas).
        exchanges: Pedidos com sucesso do `probe`, na ordem gravada.
        operations: Operações do OpenAPI por identificador.
        public: Operações marcadas como públicas em `authz.public_operations`.
        infrastructure: Caminhos de login, saúde e preparação (existem para responder sem sessão).

    Returns:
        As candidatas (até o teto) e as notas do que ficou sem teste, cada uma com o motivo.
    """
    gets = [item for item in exchanges if item.method == "GET"]
    if not gets:
        why = "O probe não trouxe nenhum GET com sucesso: não há leitura para repetir."
        return Planned((), (_note(check, None, "no_read_exchange", why),))
    tasks: list[ExchangeRecord] = []
    skips: list[AuthzNotTested] = []
    seen: set[str] = set()
    for item in gets:
        if item.operation_id in seen:
            continue
        seen.add(item.operation_id)
        skip = _skip_reason(item, operations.get(item.operation_id), public, infrastructure)
        if skip is not None:
            skips.append(_note(check, item, *skip))
        else:
            tasks.append(item)
    cap = OPERATION_CAP[check]
    over = len(tasks) - cap
    if over > 0:
        why = (
            f"Teto de {cap} operações por execução; {over} ficaram sem teste. "
            "Use `authz.public_operations` para tirar operações públicas e rode de novo."
        )
        skips.append(_note(check, None, "budget_exhausted", why))
    return Planned(tuple(tasks[:cap]), tuple(skips))
