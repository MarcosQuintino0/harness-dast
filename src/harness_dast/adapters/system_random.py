"""Implementação real da porta `RandomSource`."""

import secrets


class SystemRandom:
    """Segredos descartáveis com aleatoriedade criptográfica do sistema operacional."""

    def token_hex(self, nbytes: int) -> str:
        """Devolve `2 * nbytes` dígitos hexadecimais."""
        return secrets.token_hex(nbytes)
