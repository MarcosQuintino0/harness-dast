"""Porta de emergência da execução: trava (kill switch), prazo e falha de auditoria.

O que garante: depois que uma condição de parada é vista, ela é TRAVADA até o proxy
reiniciar. Remover o arquivo-sinal não religa o tráfego: a trava existe para o caso de
emergência, e uma condição que "se desfaz sozinha" (arquivo apagado por engano, relógio
ajustado) não deve reabrir a saída. Retomar exige reiniciar o contêiner, de propósito.
O que não faz: não interrompe conexões já em andamento; as próximas requisições e as que
esperam na fila da taxa são negadas.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from time import monotonic

from harness_dast.adapters.scope_proxy.approval_watch import FileWatch
from harness_dast.adapters.scope_proxy.decision import ALLOW, Reason, Verdict, deny
from harness_dast.adapters.scope_proxy.gate_watch import GateWatch
from harness_dast.adapters.scope_proxy.policy import ApprovalBinding
from harness_dast.adapters.scope_proxy.watch_diagnostic import Detection, WatchCause
from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.window import ensure_any_window_open


class RunGate:
    """Decide se a execução ainda pode enviar tráfego."""

    def __init__(
        self,
        *,
        kill_flag: Path,
        deadline: datetime,
        now: Callable[[], datetime],
        binding: ApprovalBinding | None = None,
        approval_dir: Path = Path("/approvals"),
        profile_dir: Path = Path("/product"),
        monitored: bool = False,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        """Cria a porta.

        Args:
            kill_flag: Caminho do arquivo-sinal; a existência dele aciona a trava.
            deadline: Instante (com fuso) a partir do qual tudo é negado.
            now: Relógio com fuso; entra por parâmetro para os testes.
            binding: Vinculo das fontes gerenciadas.
            approval_dir: Diretorio da aprovacao.
            profile_dir: Diretorio do perfil.
            monitored: Usa vigia assincrona para as fontes locais.
            monotonic_clock: Relogio monotono para medir idade da verificacao.
        """
        self._kill_flag = kill_flag
        self._deadline = deadline
        self._now = now
        self._latched: Reason | None = None
        self._binding = binding
        self._watches = (
            ()
            if binding is None
            else (
                FileWatch(
                    approval_dir / f"{binding.product}.json",
                    binding.approval_sha256,
                    product=binding.product,
                ),
                FileWatch(profile_dir / "target.yml", binding.profile_sha256),
            )
        )

        self._watch = GateWatch(self._detect_files, monotonic_clock) if monitored else None

    def close(self) -> None:
        """Invalida a vigia sem aguardar leitura bloqueada."""
        if self._watch is not None:
            self._watch.close()

    def mark_audit_failure(self) -> None:
        """Trava tudo porque a trilha de auditoria deixou de ser gravada."""
        self._latched = self._latched or Reason.AUDIT_FAILURE

    def check(self) -> Verdict:
        """Confere trava, prazo e falha de auditoria, nesta ordem de prioridade."""
        if self._latched is None:
            self._latched = self._detect()
        return ALLOW if self._latched is None else deny(self._latched)

    def _detect(self) -> Reason | None:
        if self._watch is None:
            detection = self._detect_files()
            file_reason = None if detection is None else detection.reason
        else:
            file_reason = self._watch.check()
        if file_reason is not None:
            return file_reason
        now = self._now()
        if now >= self._deadline:
            return Reason.RUN_EXPIRED
        if self._binding is not None:
            try:
                self._binding.authorization.ensure_valid(now)
                ensure_any_window_open(self._binding.windows, now)
            except (ConfigError, ScopeViolation):
                return Reason.RUN_EXPIRED
        return None

    def _detect_files(self) -> Detection | None:
        try:
            self._kill_flag.parent.stat()
            try:
                self._kill_flag.lstat()
            except FileNotFoundError:
                pass
            else:
                return Detection(Reason.KILL_SWITCH, WatchCause.STOP)
        except OSError:
            return Detection(Reason.KILL_SWITCH, WatchCause.STOP)
        for watch in self._watches:
            cause = watch.failure()
            if cause is not None:
                return Detection(Reason.APPROVAL_CHANGED, cause)
        return None
