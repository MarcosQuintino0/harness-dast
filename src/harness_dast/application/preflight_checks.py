"""Auxiliares do `preflight` (e do `doctor`): transformam passos e erros em `PreflightCheck`.

As conferências de autorização, janela e presença de segredos vivem aqui para que `preflight`
e `doctor` apliquem a MESMA regra, com os mesmos textos.
"""

from collections.abc import Callable, Iterable
from datetime import datetime

from harness_dast.application.common_ports import SecretProvider, SecretVault
from harness_dast.application.preflight_report import CheckKind, PreflightCheck
from harness_dast.domain.errors import (
    HarnessError,
    ScopeViolation,
    SecretBackendError,
    StackStale,
)
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.secret_ref import SecretRef
from harness_dast.domain.window import ensure_any_window_open


def _kind(error: HarnessError) -> CheckKind:
    return "scope" if isinstance(error, ScopeViolation) else "environment"


def failure_check(check_id: str, error: HarnessError) -> PreflightCheck:
    """Converte um erro do harness em verificação que falhou (mensagem mais dica).

    Raises:
        StackStale: Sempre repassada: pilha desatualizada não é falha do ambiente do alvo.
    """
    if isinstance(error, StackStale):
        raise error
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


def authorization_window_checks(
    profile: ProductProfile, now: datetime
) -> tuple[PreflightCheck, PreflightCheck]:
    """Verificações `authorization` (validade da carta) e `window` (janela aberta agora)."""
    authorization = scope_check(
        "authorization",
        lambda: profile.scope.authorization.ensure_valid(now),
        "A autorização formal vale agora.",
    )
    window = scope_check(
        "window",
        lambda: ensure_any_window_open(profile.scope.windows, now),
        "Há uma janela de execução aberta agora.",
    )
    return (authorization, window)


def secret_presence_check(
    alias: str,
    fields: Iterable[tuple[str, SecretRef]],
    secrets: SecretProvider,
    vault: SecretVault,
) -> PreflightCheck:
    """Diz se os segredos de uma conta estão definidos, sem nunca expor o valor.

    O relatório cita o apelido e o campo (`user_a.password`); o NOME da variável de ambiente
    só vai em `operator_detail`, que não entra no JSON. Os valores lidos são registrados no
    `vault` para mascaramento.
    """
    check_id = f"secrets:{alias}"
    try:
        resolved = [(name, ref, secrets.resolve(ref)) for name, ref in fields]
    except SecretBackendError as error:
        return failure_check(check_id, error)
    for _, _, value in resolved:
        if value:
            vault.register(value)
    missing = [(name, ref) for name, ref, value in resolved if not value]
    if not missing:
        return PreflightCheck(
            id=check_id, ok=True, detail="Todos os segredos da conta estão definidos."
        )
    names = ", ".join(f"{alias}.{name}" for name, _ in missing)
    steps = [_how_to_define(ref) for _, ref in missing]
    return PreflightCheck(
        id=check_id,
        ok=False,
        detail=(
            f"Segredo ausente ou vazio: {names}. Defina o que o secret_ref indica: variável de "
            "ambiente (env:) ou cofre (keyring:, gravado pela pessoa com hdast secret set)."
        ),
        operator_detail=" ".join(steps),
    )


def _how_to_define(ref: SecretRef) -> str:
    if ref.kind == "keyring":
        return f"Cofre: rode, num terminal, `hdast secret set {ref.name}` (pede o valor oculto)."
    return f"Variável de ambiente a definir: {ref.name}."
