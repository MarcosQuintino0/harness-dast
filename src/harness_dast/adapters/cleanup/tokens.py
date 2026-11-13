"""Fonte do token de confirmação (implementa `TokenSource`)."""

import secrets


class SecretsTokenSource:
    """Sorteia tokens com o gerador criptográfico do sistema operacional."""

    def new_token(self) -> str:
        """Devolve `hdc-` mais 192 bits aleatórios em base64 seguro para URL."""
        return "hdc-" + secrets.token_urlsafe(24)
