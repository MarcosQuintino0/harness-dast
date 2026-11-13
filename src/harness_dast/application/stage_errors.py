"""Tradução do estado final de cada etapa (`preflight`, `probe`, `scan`) no erro de saída.

Regra única, usada pelos comandos soltos e pelo `run`: janela fechada e prazo esgotado são
escopo (3); falha da ferramenta externa é 5; alvo sem resposta é 6; login recusado no meio do
`scan` é 4. Uma etapa que terminou bem devolve `None`.
"""

from harness_dast.application.preflight_report import PreflightReport
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.errors import (
    ExternalToolError,
    HarnessError,
    PreflightError,
    ScopeViolation,
    TargetError,
)
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.scan_result import ScanResult


def preflight_failure(report: PreflightReport) -> HarnessError:
    """Erro (e código de saída) de um preflight que não passou.

    Falha de autorização ou janela é escopo (3); qualquer outra, preflight (4).
    """
    failed = report.first_failure()
    message = f"Preflight não passou: {failed.id}." if failed else "Preflight não passou."
    hint = failed.detail if failed else None
    if failed is not None and failed.kind == "scope":
        return ScopeViolation(message, hint=hint)
    return PreflightError(message, hint=hint)


def probe_stop_error(result: ProbeResult) -> HarnessError | None:
    """Erro correspondente à parada antecipada do `probe`, ou `None` se completou."""
    message = result.stop_message or "O probe parou antes do fim."
    if result.status in {"stopped_window", "stopped_deadline"}:
        return ScopeViolation(message, hint="O resultado parcial está em data e em probe.json.")
    if result.status == "stopped_zap":
        return ExternalToolError(message, hint="Confira o ZAP e rode o probe de novo.")
    if result.status == "stopped_target_unresponsive":
        return TargetError(message, hint="Aguarde o alvo se recuperar antes de repetir o probe.")
    return None


def scan_stop_error(result: ScanResult) -> HarnessError | None:
    """Erro correspondente à parada antecipada do `scan`, ou `None` se completou."""
    message = result.stop_message or "O scan parou antes do fim."
    hint = "O resultado parcial está em data e em scan.json; rode 'hdast report' se quiser."
    if result.status in {"stopped_window", "stopped_deadline"}:
        return ScopeViolation(message, hint=hint)
    if result.status == "stopped_auth":
        return PreflightError(message, hint=hint)
    if result.status == "stopped_zap":
        return ExternalToolError(message, hint=hint)
    if result.status == "stopped_target_unresponsive":
        return TargetError(message, hint=hint)
    return None


def authz_stop_error(result: AuthzResult) -> HarnessError | None:
    """Erro correspondente à parada antecipada do `authz`, ou `None` se completou.

    Achado de autorização NÃO é erro: é dado (o `report` é o dono do código 1).
    """
    message = result.stop_message or "O authz parou antes do fim."
    hint = "O resultado parcial está em data e em authz.json."
    if result.status in {"stopped_window", "stopped_deadline"}:
        return ScopeViolation(message, hint=hint)
    if result.status == "stopped_zap":
        return ExternalToolError(message, hint="Confira o ZAP e rode o authz de novo.")
    if result.status == "stopped_target_unresponsive":
        return TargetError(message, hint="Aguarde o alvo se recuperar antes de repetir o authz.")
    return None
