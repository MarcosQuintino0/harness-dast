"""Arquivo de segredos do Nuclei (`-sf`) com o token de login (ADR 0122).

O que garante:
- O conteúdo é YAML no formato `static` / `type: header` do Nuclei, com todo valor escrito como
  texto entre aspas de JSON (um token com aspas, quebra de linha ou `:` nunca vira outra chave) e
  o nome do cabeçalho conferido como token HTTP.
- O arquivo nasce num diretório privado (`0700`) criado só para ele, com `O_EXCL` e modo `0600`; no
  Linux o diretório fica em memória (`/dev/shm`, tmpfs). Depois de escrito vira `0400` e passa ao
  dono do usuário do contêiner (uid 10002 do `docker/nuclei/Dockerfile`), quando o sistema permite.
- `remove` apaga o arquivo e o diretório; só apaga o que este objeto criou.

Limitações:
- Sem privilégio para trocar o dono (usuário comum no Linux), o arquivo fica `0444` dentro do
  diretório privado `0700`: o contêiner (outro uid) precisa conseguir ler e o Docker monta o arquivo
  pelo inode, então só o dono do diretório alcança o conteúdo no host.
- No Windows não há `chown` nem modo de arquivo POSIX: o arquivo fica num diretório temporário do
  usuário (herda a ACL do perfil dele) e só ganha o atributo somente leitura. O Docker Desktop
  mostra o arquivo ao contêiner pela montagem, e a proteção real é o diretório do usuário.
O que não faz: não monta o arquivo no contêiner nem registra o conteúdo em log.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Final

from harness_dast.application.nuclei_ports import NucleiSecret
from harness_dast.domain.errors import ConfigError

__all__ = ["NUCLEI_CONTAINER_UID", "NucleiSecretsFile", "render_secrets_yaml"]

NUCLEI_CONTAINER_UID: Final = 10002
"""uid e gid do usuário do contêiner (`docker/nuclei/Dockerfile`, `compose.yaml`)."""
_SHM = Path("/dev/shm")  # noqa: S108 - tmpfs do Linux: é justamente onde o segredo não vai a disco
_HEADER_NAME = re.compile(r"[A-Za-z0-9-]{1,64}")
_DOMAIN = re.compile(r"[A-Za-z0-9.:\[\]-]{1,260}")
_DIR_PREFIX = "hdast-nuclei-sf-"
_FILE_NAME = "secrets.yaml"

type Chown = Callable[[Path, int, int], None]


def render_secrets_yaml(secret: NucleiSecret) -> str:
    """Texto YAML do arquivo `-sf` para um cabeçalho em domínios fixos.

    Raises:
        ConfigError: Nome de cabeçalho, domínio ou valor inválido (vazio ou com controle).
    """
    if not _HEADER_NAME.fullmatch(secret.header):
        raise ConfigError(
            "Nome de cabeçalho inválido para o login do Nuclei.",
            hint="Confira auth.token_header no target.yml: só letras, dígitos e hífen.",
        )
    if not secret.domains or not all(_DOMAIN.fullmatch(domain) for domain in secret.domains):
        raise ConfigError(
            "Domínio inválido para o login do Nuclei.", hint="Confira environment.base_url."
        )
    if not secret.value or not secret.value.isprintable():
        raise ConfigError(
            "O valor do cabeçalho de login não pôde ser gravado com segurança.",
            hint="Confira o token que o login devolveu (vazio ou com caractere de controle).",
        )
    domains = "".join(f"      - {_quote(domain)}\n" for domain in secret.domains)
    return (
        "static:\n"
        "  - type: header\n"
        "    domains:\n"
        f"{domains}"
        "    headers:\n"
        f"      - key: {_quote(secret.header)}\n"
        f"        value: {_quote(secret.value)}\n"
    )


def _quote(text: str) -> str:
    # Texto entre aspas de JSON é um escalar YAML válido: nenhum caractere do valor escapa dele.
    return json.dumps(text, ensure_ascii=True)


def _system_chown() -> Chown | None:
    chown: Chown | None = getattr(os, "chown", None)
    return chown


def _default_base() -> Path | None:
    if sys.platform.startswith("linux") and _SHM.is_dir() and os.access(_SHM, os.W_OK):
        return _SHM
    return None


class NucleiSecretsFile:
    """Implementa `NucleiSecretsWriter` (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        base_dir: Path | None = None,
        owner_id: int = NUCLEI_CONTAINER_UID,
        chown: Chown | None = None,
    ) -> None:
        """Cria o gravador.

        Args:
            base_dir: Pasta em que o diretório privado nasce; o padrão é `/dev/shm` no Linux e a
                pasta temporária do usuário nos demais sistemas.
            owner_id: uid e gid que passam a ser donos do arquivo (o usuário do contêiner).
            chown: Troca de dono; o padrão é `os.chown` quando o sistema o tem. Injetada nos testes.
        """
        self._base = _default_base() if base_dir is None else base_dir
        self._owner_id = owner_id
        self._chown = _system_chown() if chown is None else chown
        self._created: dict[Path, Path] = {}

    def write(self, secret: NucleiSecret) -> Path:
        """Grava o arquivo `-sf` e devolve o caminho (nunca o conteúdo).

        Raises:
            ConfigError: Conteúdo inválido ou falha de escrita; nada fica no disco.
        """
        text = render_secrets_yaml(secret)
        try:
            directory = Path(tempfile.mkdtemp(prefix=_DIR_PREFIX, dir=self._base))
        except OSError:
            raise ConfigError(
                "Não consegui criar a pasta privada do arquivo de segredos do Nuclei.",
                hint="Confira o espaço e a permissão da pasta temporária.",
            ) from None
        path = directory / _FILE_NAME
        try:
            self._create(path, text)
            self._harden(path)
        except OSError:
            self._wipe(directory)
            raise ConfigError(
                "Não consegui gravar o arquivo de segredos do Nuclei.",
                hint="Confira o espaço e a permissão da pasta temporária.",
            ) from None
        except BaseException:
            self._wipe(directory)
            raise
        self._created[path] = directory
        return path

    def remove(self, path: Path) -> None:
        """Apaga o arquivo e a pasta privada que `write` criou; ignora o que já sumiu.

        Raises:
            ConfigError: O arquivo existe e não pôde ser apagado.
        """
        directory = self._created.pop(path, None)
        if directory is None:
            return
        self._wipe(directory)
        if directory.exists():
            raise ConfigError(
                f"Não consegui apagar o arquivo de segredos do Nuclei em {directory}.",
                hint="Apague essa pasta agora: ela contém o token da conta de teste.",
            )

    @staticmethod
    def _create(path: Path, text: str) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    def _harden(self, path: Path) -> None:
        owned = False
        if self._chown is not None:
            try:
                self._chown(path, self._owner_id, self._owner_id)
                owned = True
            except OSError:
                owned = False
        # Sem poder trocar o dono, o contêiner (outro uid) só lê se o arquivo for legível por todos;
        # a pasta `0700` continua sendo a barreira no host.
        path.chmod(0o400 if owned else 0o444)

    @staticmethod
    def _wipe(directory: Path) -> None:
        for child in directory.glob("*"):
            try:
                child.chmod(0o600)  # no Windows, o atributo somente leitura impede o unlink
            except OSError:
                continue
        shutil.rmtree(directory, ignore_errors=True)
