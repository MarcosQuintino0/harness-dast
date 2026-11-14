"""Sessão de uma credencial adulterada: o que o teste "token adulterado" envia (ADR 0039).

`TamperedSession` implementa `SessionHooks` e devolve SÓ o cabeçalho de autenticação com o valor
adulterado. Não tem login, não busca token CSRF e não repete nada: um 401 é a resposta esperada.
O valor adulterado é registrado no `SecretVault` antes de existir qualquer pedido, para ser
mascarado em mensagem, log e trecho de resposta. Nunca sai deste objeto para artefato algum.
"""

from harness_dast.application.account_session import AuthCredential
from harness_dast.application.ports import SecretVault


class TamperedSession:
    """Sessão que envia uma credencial adulterada no lugar da original."""

    def __init__(self, credential: AuthCredential, tampered: str, vault: SecretVault) -> None:
        """Cria a sessão e registra o valor adulterado para mascaramento.

        Args:
            credential: Credencial original da conta (só dá o cabeçalho e o esquema).
            tampered: Valor adulterado do token ou da chave.
            vault: Registro de segredos a mascarar.
        """
        vault.register(tampered)
        self._header = credential.header
        self._value = credential.header_value(tampered)

    def request_headers(self, method: str) -> tuple[tuple[str, str], ...]:
        """Só o cabeçalho de autenticação adulterado (sem CSRF, sem cookie)."""
        del method
        return ((self._header, self._value),)

    def relogin(self) -> None:
        """Não faz nada: um token adulterado nunca dispara novo login."""

    def refresh_csrf(self) -> None:
        """Não faz nada: o pedido adulterado não busca token CSRF."""
