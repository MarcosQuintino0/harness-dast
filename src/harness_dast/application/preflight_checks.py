"""Auxiliares do `preflight`: transformam passos e erros em `PreflightCheck`."""

from collections.abc import Callable

from harness_dast.application.preflight_report import CheckKind, PreflightCheck
from harness_dast.domain.errors import HarnessError, ScopeViolation


def _kind(error: HarnessError) -> CheckKind:
    return "scope" if isinstance(error, ScopeViolation) else "environment"


def failure_check(check_id: str, error: HarnessError) -> PreflightCheck:
    """Converte um erro do harness em verificação que falhou (mensagem mais dica)."""
    detail = f"{error.message} {error.hint or ''}".strip()
    return PreflightCheck(id=check_id, ok=False, detail=detail, kind=_kind(error))


def run_step(check_id: str, action: Callable[[], None], ok_detail: str) -> PreflightCheck:
    """Executa um passo; `HarnessError` vira verificação que falhou, sucesso vira `ok_detail`."""
    try:
        action()
    except HarnessError as error:
        return failure_check(check_id, error)
    return PreflightCheck(id=check_id, ok=True, detail=ok_detail)


def scope_check(check_id: str, action: Callable[[], None], ok_detail: str) -> PreflightCheck:
    """Como `run_step`, para autorização e janela: só `ScopeViolation` é capturada."""
    try:
        action()
    except ScopeViolation as error:
        return failure_check(check_id, error)
    return PreflightCheck(id=check_id, ok=True, kind="scope", detail=ok_detail)


def not_run_checks() -> tuple[PreflightCheck, ...]:
    """Verificações de rede marcadas como não executadas (escopo não permite enviar)."""
    return tuple(
        PreflightCheck(
            id=name,
            ok=False,
            detail="Não executado: autorização ou janela não permitem enviar requisições.",
        )
        for name in ("zap", "target_health")
    )
