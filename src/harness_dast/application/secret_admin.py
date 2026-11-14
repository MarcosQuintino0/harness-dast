"""Caso de uso `secret`: a PESSOA grava, lista e remove segredos do cofre do sistema.

Nunca devolve nem registra o valor. Gravar e remover exigem terminal interativo (a CLI o
calcula e passa em `interactive`), como a confirmação da limpeza (ADR 0025): quem roda sem
terminal, como um agente de IA, é recusado. Ver ADR 0030.
"""

from pydantic import BaseModel, ConfigDict

from harness_dast.application.ports import (
    CredentialStore,
    ProfileRepository,
    SecretPrompt,
    SecretVault,
)
from harness_dast.application.secret_refs import profile_secret_refs
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.secret_ref import is_valid_secret_name

_COMMAND = "hdast secret"


class SecretWriteReport(BaseModel):
    """Resultado de `secret set`: só o nome e se substituiu um valor antigo."""

    model_config = ConfigDict(frozen=True)

    name: str
    replaced: bool


class SecretDeleteReport(BaseModel):
    """Resultado de `secret delete`: `removed` é `False` se a pessoa recusou ou não existia."""

    model_config = ConfigDict(frozen=True)

    name: str
    removed: bool
    existed: bool


class SecretEntry(BaseModel):
    """Um segredo `keyring:` citado pelo perfil: nome, onde é usado e se está no cofre."""

    model_config = ConfigDict(frozen=True)

    name: str
    used_by: tuple[str, ...]
    present: bool


class SecretListReport(BaseModel):
    """Resultado de `secret list`: nunca traz valor nem tamanho."""

    model_config = ConfigDict(frozen=True)

    product: str
    entries: tuple[SecretEntry, ...]


class SecretAdmin:
    """Gestão do cofre feita pela pessoa."""

    def __init__(
        self,
        profiles: ProfileRepository,
        store: CredentialStore,
        prompt: SecretPrompt,
        vault: SecretVault,
    ) -> None:
        """Cria o caso de uso.

        Args:
            profiles: Repositório de perfis (para `list`).
            store: Cofre de credenciais.
            prompt: Prompt de terminal (valor oculto e confirmação de remoção).
            vault: Registro de segredos a mascarar (recebe o valor digitado).
        """
        self._profiles = profiles
        self._store = store
        self._prompt = prompt
        self._vault = vault

    def set_secret(self, name: str, *, interactive: bool) -> SecretWriteReport:
        """Lê o valor por prompt oculto e o guarda no cofre sob `name`.

        Raises:
            ConfigError: Nome inválido, sem terminal interativo, ou valor vazio.
            SecretBackendError: Cofre indisponível.
        """
        self._check_name(name)
        self._require_terminal(interactive, "gravar")
        value = self._prompt.read_value(name)
        if not value.strip():
            raise ConfigError(
                "O valor digitado está vazio; nada foi gravado.",
                hint=f"Rode `{_COMMAND} set {name}` de novo e digite o valor.",
            )
        self._vault.register(value)
        replaced = self._store.read(name) is not None
        self._store.write(name, value)
        return SecretWriteReport(name=name, replaced=replaced)

    def delete_secret(self, name: str, *, interactive: bool) -> SecretDeleteReport:
        """Remove `name` do cofre, depois que a pessoa digitar o nome para confirmar.

        Raises:
            ConfigError: Nome inválido ou sem terminal interativo.
            SecretBackendError: Cofre indisponível.
        """
        self._check_name(name)
        self._require_terminal(interactive, "remover")
        existed = self._store.read(name) is not None
        if not existed:
            return SecretDeleteReport(name=name, removed=False, existed=False)
        if not self._prompt.confirm_removal(name):
            return SecretDeleteReport(name=name, removed=False, existed=True)
        self._store.remove(name)
        return SecretDeleteReport(name=name, removed=True, existed=True)

    def list_secrets(self, product: str) -> SecretListReport:
        """Lista os `keyring:` do perfil de `product` e se cada um existe no cofre.

        Raises:
            ConfigError: Produto ou perfil inválido.
            SecretBackendError: Cofre indisponível (só se o perfil cita algum `keyring:`).
        """
        profile = self._profiles.load(product)
        used: dict[str, list[str]] = {}
        for field, ref in profile_secret_refs(profile):
            if ref.kind == "keyring":
                used.setdefault(ref.name, []).append(field)
        entries = tuple(
            SecretEntry(
                name=name,
                used_by=tuple(fields),
                present=self._present(name),
            )
            for name, fields in sorted(used.items())
        )
        return SecretListReport(product=product, entries=entries)

    def _present(self, name: str) -> bool:
        value = self._store.read(name)
        return value is not None and bool(value.strip())

    @staticmethod
    def _check_name(name: str) -> None:
        if not is_valid_secret_name(name):
            raise ConfigError(
                "Nome de segredo inválido.",
                hint=(
                    "Use o NOME que aparece em secret_ref: keyring:NOME, em maiúsculas, "
                    "dígitos e '_', sem o prefixo HDAST_ (por exemplo AGENDA_USER_A_SENHA)."
                ),
            )

    @staticmethod
    def _require_terminal(interactive: bool, action: str) -> None:
        if not interactive:
            raise ConfigError(
                f"Só uma pessoa, num terminal interativo, pode {action} segredo do cofre.",
                hint=(
                    "Abra um terminal seu e rode o comando lá; o valor é digitado no prompt "
                    "oculto. Não existe flag, arquivo nem variável que o dispense."
                ),
            )
