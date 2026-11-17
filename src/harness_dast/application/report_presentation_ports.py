"""Porta de leitura dos arquivos consultivos da apresenta??o."""

from typing import Protocol

from harness_dast.domain.human_confirmation import HumanConfirmations
from harness_dast.domain.report.presentation import Calibration
from harness_dast.domain.verification import VerificationFile


class PresentationFiles(Protocol):
    """Fronteira de leitura dos arquivos consultivos da execução e da calibração."""

    def verification(self, product: str, run_id: str) -> VerificationFile | None:
        """Lê verificação validada ou None se ausente; inválida levanta ConfigError."""
        ...

    def confirmations(self, product: str, run_id: str) -> HumanConfirmations | None:
        """Lê confirmações validadas ou None se ausentes; inválidas levantam ConfigError."""
        ...

    def calibration(self) -> Calibration | None:
        """Lê calibração validada ou None se ausente; inválida levanta ConfigError."""
        ...
