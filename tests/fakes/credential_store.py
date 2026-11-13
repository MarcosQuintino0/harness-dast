"""Falsos do cofre: em memória, com falha injetável, e um backend de teste do keyring."""

from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from harness_dast.domain.errors import SecretBackendError


class InMemoryCredentialStore:
    """`CredentialStore` falso: dicionário `NOME -> valor`, com cofre indisponível opcional."""

    def __init__(self, values: dict[str, str] | None = None, *, broken: bool = False) -> None:
        self.values = dict(values or {})
        self.broken = broken

    def _check(self) -> None:
        if self.broken:
            raise SecretBackendError(
                "O cofre de credenciais não está disponível.", hint="Use secret_ref: env:NOME."
            )

    def read(self, name: str) -> str | None:
        self._check()
        return self.values.get(name) or None

    def write(self, name: str, value: str) -> None:
        self._check()
        self.values[name] = value

    def remove(self, name: str) -> bool:
        self._check()
        return self.values.pop(name, None) is not None


class MemoryBackend(KeyringBackend):
    """Backend de teste do `keyring` (em memória); NUNCA toca o cofre real da máquina."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]  # __init__ do keyring sem anotação
        self.data: dict[tuple[str, str], str] = {}
        self.error: Exception | None = None

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error

    def get_password(self, service: str, username: str) -> str | None:
        self._raise()
        return self.data.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._raise()
        self.data[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._raise()
        if (service, username) not in self.data:
            raise PasswordDeleteError(service)
        del self.data[(service, username)]
