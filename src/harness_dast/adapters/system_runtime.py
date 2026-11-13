"""Implementações reais das portas `Sleeper` e `EntropySource`."""

import secrets
import time


class SystemSleeper:
    """Espera de verdade (`time.sleep`)."""

    def sleep(self, seconds: float) -> None:
        """Bloqueia por `seconds` segundos; valores negativos viram zero."""
        time.sleep(max(seconds, 0.0))


class SystemEntropy:
    """Aleatoriedade criptográfica do sistema operacional."""

    def hex_suffix(self) -> str:
        """Quatro dígitos hexadecimais minúsculos para o `RunId`."""
        return secrets.token_hex(2)

    def seed(self) -> int:
        """Semente inteira de 32 bits para os geradores de dados."""
        return secrets.randbits(32)
