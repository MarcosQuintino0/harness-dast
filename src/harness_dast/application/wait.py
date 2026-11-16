"""Caso de uso de espera, sem acesso ao alvo."""

from collections.abc import Callable

from harness_dast.application.ports import WaitReader
from harness_dast.domain.wait import WaitResult


class WaitRun:
    """Aguarda término ou prazo com relógio e pausa injetados."""

    def __init__(
        self, reader: WaitReader, monotonic: Callable[[], float], sleep: Callable[[float], None]
    ) -> None:
        """Recebe leitor, relógio monotônico e função de pausa."""
        self._reader = reader
        self._monotonic = monotonic
        self._sleep = sleep

    def execute(self, run_id: str, timeout: int) -> WaitResult:
        """Retorna imediatamente ao terminar ou parar; no prazo retorna a última observação."""
        deadline = self._monotonic() + timeout
        while True:
            result = self._reader.read(run_id)
            remaining = deadline - self._monotonic()
            if result.state in ("finished", "stopped") or remaining <= 0:
                return result
            self._sleep(min(2.0, remaining))
