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

from harness_dast.adapters.scope_proxy.decision import ALLOW, Reason, Verdict, deny


class RunGate:
    """Decide se a execução ainda pode enviar tráfego."""

    def __init__(
        self,
        *,
        kill_flag: Path,
        deadline: datetime,
        now: Callable[[], datetime],
    ) -> None:
        """Cria a porta.

        Args:
            kill_flag: Caminho do arquivo-sinal; a existência dele aciona a trava.
            deadline: Instante (com fuso) a partir do qual tudo é negado.
            now: Relógio com fuso; entra por parâmetro para os testes.
        """
        self._kill_flag = kill_flag
        self._deadline = deadline
        self._now = now
        self._latched: Reason | None = None

    def mark_audit_failure(self) -> None:
        """Trava tudo porque a trilha de auditoria deixou de ser gravada."""
        self._latched = self._latched or Reason.AUDIT_FAILURE

    def check(self) -> Verdict:
        """Confere trava, prazo e falha de auditoria, nesta ordem de prioridade."""
        if self._latched is None:
            self._latched = self._detect()
        return ALLOW if self._latched is None else deny(self._latched)

    def _detect(self) -> Reason | None:
        # Se não for possível nem saber se o arquivo existe, a resposta segura é travar.
        try:
            if self._kill_flag.exists():
                return Reason.KILL_SWITCH
        except OSError:
            return Reason.KILL_SWITCH
        if self._now() >= self._deadline:
            return Reason.RUN_EXPIRED
        return None
