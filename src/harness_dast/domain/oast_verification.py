"""Decisão de observabilidade OAST a partir de fatos, sem acesso à pilha."""

from typing import TYPE_CHECKING, Literal

from pydantic import model_validator

from harness_dast.domain.api_schema import ApiModel

if TYPE_CHECKING:
    from harness_dast.domain.scan_result import ScanResult


class OastVerification(ApiModel):
    """Disponibilidade da observação de retorno, sem afirmar que houve retorno.

    Attributes:
        zap: Se os retornos das regras do ZAP são observáveis.
        ssrf: Se os retornos do SSRF guiado são observáveis.
        reason: Motivo controlado quando não verificável.
    """

    zap: Literal["verifiable", "unverifiable"]
    ssrf: Literal["verifiable", "unverifiable"]
    reason: str | None = None

    @model_validator(mode="after")
    def require_reason(self) -> "OastVerification":
        """Recusa lacuna sem motivo para a pessoa leitora."""
        if (self.zap == "unverifiable" or self.ssrf == "unverifiable") and not self.reason:
            raise ValueError("estado não verificável exige motivo")
        return self


def callback_unavailable() -> OastVerification:
    """Registra que o serviço Callback do ZAP não pôde ser configurado."""
    return OastVerification(
        zap="unverifiable",
        ssrf="unverifiable",
        reason="Não foi possível configurar o Callback OAST do ZAP.",
    )


def mark_ssrf_unobservable(verification: OastVerification) -> OastVerification:
    """Registra perda ou ausência do observador do SSRF, preservando estado do ZAP."""
    return OastVerification(
        zap=verification.zap,
        ssrf="unverifiable",
        reason="Observador do SSRF guiado indisponível ou interrompido.",
    )


def combine_oast_availability(bridge: bool | None, callback: bool | None) -> bool | None:
    """Combina os fatos: uma falha confirmada prevalece sobre estado desconhecido."""
    if bridge is False or callback is False:
        return False
    return True if bridge is True and callback is True else None


def decide_oast_verification(available: bool | None) -> OastVerification:
    """Decide conservadoramente a partir da inspeção da ponte, sem fazer I/O."""
    if available is True:
        return OastVerification(zap="verifiable", ssrf="verifiable")
    reason = (
        "Ponte de retorno ausente ou indisponível."
        if available is False
        else "Disponibilidade da ponte de retorno desconhecida."
    )
    return OastVerification(zap="unverifiable", ssrf="unverifiable", reason=reason)


def oast_gap(scan: "ScanResult") -> str | None:
    """Explica cobertura não verificável, inclusive em artefatos antigos com OAST ligado."""
    verification = scan.oast_verification
    if not scan.policy.oast and verification is None:
        return None
    if verification is None:
        return (
            "SSRF guiado e OAST do ZAP não verificáveis: disponibilidade da ponte não registrada."
        )
    if verification.zap == "unverifiable" and verification.ssrf == "unverifiable":
        return f"SSRF guiado e OAST do ZAP não verificáveis: {verification.reason}"
    if verification.ssrf == "unverifiable":
        return f"SSRF guiado não verificável: {verification.reason}"
    if verification.zap == "unverifiable":
        return f"OAST do ZAP não verificável: {verification.reason}"
    return None
