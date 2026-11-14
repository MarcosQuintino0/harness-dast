"""Laço do teste de autorização: orquestra as verificações e monta o resultado.

O laço roda as verificações pedidas na ordem recebida, por meio do mapa `CHECK_RUNNERS`
(verificação -> função), e junta o resultado em `AuthzOutcome`. Cada verificação vive em
módulo próprio (`authz_checks_*`) e todo pedido passa por `ReplaySender` (`authz_sender`), que
usa `OperationDispatcher` sobre o `GuardedSender` (escopo, `deny_paths`, métodos, taxa,
janela, prazo, trava e auditoria). Verificação nova: uma função em módulo novo e uma linha em
`CHECK_RUNNERS`. Nenhum valor de resposta é guardado: só o veredito, os códigos e os NOMES de
campo vão para o resultado. Paradas antecipadas (janela, prazo, ZAP, alvo sem resposta)
interrompem o laço e voltam como `AuthzOutcome`; nunca são engolidas.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from harness_dast.application.authz_checks_access import run_anonymous, run_tampered
from harness_dast.application.authz_checks_mass import run_mass
from harness_dast.application.authz_checks_read import run_excessive, run_horizontal, run_vertical
from harness_dast.application.authz_checks_write import run_horizontal_write
from harness_dast.application.authz_sender import (
    AuthzSettings,
    CheckContext,
    CheckResult,
    ReplaySender,
    StopRun,
)
from harness_dast.application.run_support import DeadlineReached, WindowClosed
from harness_dast.domain.authz_config import AuthzCheck
from harness_dast.domain.authz_plan import Planned, ReplayTask
from harness_dast.domain.authz_plan_mass import MassTask
from harness_dast.domain.authz_plan_write import WriteTask
from harness_dast.domain.authz_result import (
    AuthzFinding,
    AuthzNotTested,
    CheckStatus,
    CheckSummary,
)
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.probe_result import ProbeStatus

__all__ = ["AuthzOutcome", "AuthzPlans", "AuthzRunner", "AuthzSettings"]


@dataclass(frozen=True)
class AuthzOutcome:
    """Resultado do laço.

    Attributes:
        status: `completed` ou o motivo da parada antecipada.
        stop_message: Explicação da parada.
        checks: Uma linha por verificação pedida.
        findings: Achados, na ordem das verificações.
        not_tested: O que não foi testado e por quê.
        requests_sent: Requisições enviadas.
        accounts: Contas que enviaram.
        created_resources: Recursos que um `POST` de teste deixou no alvo (ADR 0040).
    """

    status: ProbeStatus
    stop_message: str | None
    checks: tuple[CheckSummary, ...]
    findings: tuple[AuthzFinding, ...]
    not_tested: tuple[AuthzNotTested, ...]
    requests_sent: int
    accounts: tuple[str, ...]
    created_resources: int = 0


@dataclass(frozen=True)
class AuthzPlans:
    """Planos de cada verificação (calculados no domínio antes de enviar)."""

    horizontal: Planned[ReplayTask]
    excessive: Planned[ExchangeRecord]
    anonymous: Planned[ExchangeRecord]
    tampered: Planned[ExchangeRecord]
    vertical: Planned[ReplayTask]
    mass: Planned[MassTask]
    horizontal_write: Planned[WriteTask]


CheckRunner = Callable[[CheckContext, AuthzPlans], CheckResult]

CHECK_RUNNERS: dict[AuthzCheck, CheckRunner] = {
    "horizontal": lambda ctx, plans: run_horizontal(ctx, plans.horizontal),
    "excessive_data": lambda ctx, plans: run_excessive(ctx, plans.excessive),
    "anonymous_access": lambda ctx, plans: run_anonymous(ctx, plans.anonymous),
    "tampered_token": lambda ctx, plans: run_tampered(ctx, plans.tampered),
    "vertical": lambda ctx, plans: run_vertical(ctx, plans.vertical),
    "mass_assignment": lambda ctx, plans: run_mass(ctx, plans.mass),
    "horizontal_write": lambda ctx, plans: run_horizontal_write(ctx, plans.horizontal_write),
}
"""Função de cada verificação; uma verificação nova entra com uma linha aqui."""


class AuthzRunner:
    """Executa as verificações pedidas (veja o docstring do módulo)."""

    def __init__(self, settings: AuthzSettings) -> None:
        """Cria o executor.

        Args:
            settings: Entradas fixas do laço.
        """
        self._sender = ReplaySender(settings)
        self._ctx = CheckContext(settings, self._sender)

    def run(self, checks: tuple[AuthzCheck, ...], plans: AuthzPlans) -> AuthzOutcome:
        """Roda as verificações na ordem recebida.

        Returns:
            O resultado; janela fechada e prazo esgotado voltam como `stopped_window` e
            `stopped_deadline`, falha do proxy como `stopped_zap` e alvo sem resposta em
            sequência como `stopped_target_unresponsive`.
        """
        results: dict[AuthzCheck, CheckResult] = {}
        status: ProbeStatus = "completed"
        message: str | None = None
        current: AuthzCheck | None = None
        try:
            for check in checks:
                current = check
                results[check] = CHECK_RUNNERS[check](self._ctx, plans)
        except StopRun as stop:
            status, message = stop.status, stop.message
        except WindowClosed as error:
            status, message = "stopped_window", error.message
        except DeadlineReached as error:
            status, message = "stopped_deadline", error.message
        except ExternalToolError as error:
            status, message = "stopped_zap", error.message
        partial = current if status != "completed" and current not in results else None
        if partial is not None and partial in self._ctx.live:
            results[partial] = self._ctx.live[partial]
        return self._outcome(checks, results, status, message, partial)

    def _outcome(
        self,
        checks: tuple[AuthzCheck, ...],
        results: Mapping[AuthzCheck, CheckResult],
        status: ProbeStatus,
        message: str | None,
        partial: AuthzCheck | None,
    ) -> AuthzOutcome:
        summaries: list[CheckSummary] = []
        findings: list[AuthzFinding] = []
        not_tested: list[AuthzNotTested] = []
        for check in checks:
            result = results.get(check)
            if result is None:
                summaries.append(
                    CheckSummary(
                        check=check,
                        status="skipped",
                        message="Não rodou: a execução parou antes desta verificação.",
                    )
                )
                continue
            findings.extend(result.findings)
            not_tested.extend(result.not_tested)
            summaries.append(_summary(check, result, partial=check == partial))
        return AuthzOutcome(
            status=status,
            stop_message=message,
            checks=tuple(summaries),
            findings=tuple(findings),
            not_tested=tuple(not_tested),
            requests_sent=self._sender.sent,
            accounts=self._sender.accounts,
            created_resources=sum(item.created for item in results.values()),
        )


def _summary(check: AuthzCheck, result: CheckResult, *, partial: bool) -> CheckSummary:
    skipped = result.tested == 0
    done: CheckStatus = "partial" if partial else "completed"
    return CheckSummary(
        check=check,
        status="skipped" if skipped else done,
        candidates=result.candidates,
        tested=result.tested,
        findings=len(result.findings),
        message="Nenhuma operação pôde ser testada; veja not_tested." if skipped else None,
    )
