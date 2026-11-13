"""Cofre de credenciais do sistema operacional, via biblioteca `keyring` (ADR 0030)."""

from collections.abc import Callable

from keyring.backend import KeyringBackend
from keyring.backends.chainer import ChainerBackend
from keyring.errors import PasswordDeleteError

from harness_dast.domain.errors import SecretBackendError

KEYRING_SERVICE = "harness-dast"

# Só cofres do próprio sistema. Fora daqui fica o backend `fail` (sem cofre), o `null` e,
# principalmente, qualquer backend de arquivo em texto claro (pacote `keyrings.alt`) que alguém
# instale ou escolha por PYTHON_KEYRING_BACKEND ou keyringrc.cfg.
ALLOWED_BACKENDS = frozenset(
    {
        "keyring.backends.Windows.WinVaultKeyring",
        "keyring.backends.macOS.Keyring",
        "keyring.backends.SecretService.Keyring",
        "keyring.backends.libsecret.Keyring",
        "keyring.backends.kwallet.DBusKeyring",
        "keyring.backends.kwallet.DBusKeyringKWallet4",
    }
)

_HINT_NO_STORE = (
    "Em contêiner, CI ou máquina sem serviço de segredos, use secret_ref: env:NOME. No Linux, "
    "instale e desbloqueie um serviço de segredos (GNOME Keyring ou KWallet)."
)


def backend_id(backend: KeyringBackend) -> str:
    """Nome qualificado da classe do backend (`modulo.Classe`)."""
    cls = type(backend)
    return f"{cls.__module__}.{cls.__qualname__}"


def ensure_system_backend(backend: KeyringBackend) -> KeyringBackend:
    """Aceita só backend de cofre do sistema (ver `ALLOWED_BACKENDS`).

    O `ChainerBackend` (usado quando há vários cofres viáveis) vale se TODOS os que ele agrupa
    estão na lista.

    Raises:
        SecretBackendError: Backend fora da lista ou sem cofre.
    """
    if isinstance(backend, ChainerBackend):
        chained = [backend_id(item) for item in ChainerBackend.backends]
        if chained and all(item in ALLOWED_BACKENDS for item in chained):
            return backend
        raise SecretBackendError(
            "O cofre de credenciais não está disponível: nenhum backend do sistema em uso.",
            hint=_HINT_NO_STORE,
        )
    if backend_id(backend) not in ALLOWED_BACKENDS:
        raise SecretBackendError(
            f"O backend de credenciais em uso ({backend_id(backend)}) não é um cofre do "
            "sistema aceito pelo harness.",
            hint=_HINT_NO_STORE,
        )
    return backend


class KeyringCredentialStore:
    """Implementa `CredentialStore` sobre o cofre do sistema.

    O backend só é escolhido (e validado) na primeira operação: quem usa apenas `env:` nunca o
    toca. Nunca inclui o valor em exceção; a causa de uma falha aparece só pelo nome da classe.
    """

    def __init__(self, backend_factory: Callable[[], KeyringBackend]) -> None:
        """Cria o cofre.

        Args:
            backend_factory: Devolve o backend a usar (na CLI, o padrão do `keyring`; nos
                testes, um backend em memória).
        """
        self._factory = backend_factory
        self._backend: KeyringBackend | None = None

    def read(self, name: str) -> str | None:
        """Devolve o valor sob `name`, ou `None` se não existe ou está vazio."""
        backend = self._open()
        try:
            value = backend.get_password(KEYRING_SERVICE, name)
        except Exception as error:  # noqa: BLE001 - ver _fail
            raise _fail("ler", error) from None
        return value or None

    def write(self, name: str, value: str) -> None:
        """Guarda `value` sob `name`."""
        backend = self._open()
        try:
            backend.set_password(KEYRING_SERVICE, name, value)
        except Exception as error:  # noqa: BLE001 - ver _fail
            raise _fail("gravar", error) from None

    def remove(self, name: str) -> bool:
        """Apaga `name`; `False` se não existia."""
        backend = self._open()
        try:
            backend.delete_password(KEYRING_SERVICE, name)
        except PasswordDeleteError:
            return False
        except Exception as error:  # noqa: BLE001 - ver _fail
            raise _fail("remover", error) from None
        return True

    def _open(self) -> KeyringBackend:
        if self._backend is None:
            try:
                candidate = self._factory()
            except Exception as error:  # noqa: BLE001 - ver _fail
                raise _fail("abrir", error) from None
            self._backend = ensure_system_backend(candidate)
        return self._backend


def _fail(action: str, error: Exception) -> SecretBackendError:
    """Converte falha de backend em erro claro, sem repetir a mensagem dela.

    Os backends levantam tipos próprios e imprevisíveis (o do Windows, `pywintypes.error`, nem
    herda de `KeyringError`), por isso o adaptador captura `Exception` neste único ponto. A
    mensagem original pode conter detalhes do sistema; só o nome da classe vai ao texto, e a
    causa é descartada (`from None`) para não chegar a log nem a artefato.
    """
    return SecretBackendError(
        f"Falha ao {action} o segredo no cofre do sistema ({type(error).__name__}).",
        hint=(
            "Confira se o cofre está desbloqueado e acessível a esta sessão. "
            "Em contêiner ou CI, use secret_ref: env:NOME."
        ),
    )
