"""Regra CORS e achados de configuração, sem E/S."""

from typing import Literal

from harness_dast.domain.authz_finding_build import build_finding
from harness_dast.domain.authz_result import AuthzFinding
from harness_dast.domain.probe_exchange import ExchangeRecord

CorsPolicy = Literal["reflected_credentials", "wildcard"]


def classify_cors(
    origin: str, allow_origin: str | None, credentials: str | None
) -> CorsPolicy | None:
    """Reconhece políticas que o navegador aceita para a origem enviada."""
    if allow_origin == origin and credentials == "true":
        return "reflected_credentials"
    if allow_origin == "*" and credentials != "true":
        return "wildcard"
    return None


def cors_finding(
    product: str, exchange: ExchangeRecord, role: str | None, status: int, policy: CorsPolicy
) -> AuthzFinding:
    """Cria achado estável por produto e política, preservando a operação de prova."""
    high = policy == "reflected_credentials"
    finding = build_finding(
        product=product,
        technique="authz_cors",
        title="CORS reflete origem com credenciais" if high else "CORS permite qualquer origem",
        severity="high" if high else "low",
        operation_id=exchange.operation_id,
        method="GET",
        path_template="/",
        actor=(exchange.account, role),
        owner=None,
        statuses=(None, status),
        fields=(policy,),
        evidence=(
            "A resposta refletiu uma origem estranha e permitiu credenciais."
            if high
            else "A resposta permitiu qualquer origem sem credenciais."
        ),
        description=(
            "Uma origem externa pode ler respostas permitidas pela política CORS; o impacto "
            "depende da autenticação e dos dados expostos."
        ),
        solution="Restringir origens e permitir credenciais apenas para origens confiáveis.",
    )
    return finding.model_copy(update={"path_template": exchange.path})
