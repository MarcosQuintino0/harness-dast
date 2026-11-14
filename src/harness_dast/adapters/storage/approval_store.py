"""Aprovações humanas do escopo em arquivos: `<estado>/approvals/<produto>.json` (ADR 0037).

Implementa a porta `ApprovalStore`. Mora na pasta de estado (`HDAST_STATE_DIR`), fora da pasta
do produto e de `runs/`, para que a permissão do agente possa negar a edição dela. Gravação
atômica por arquivo temporário (modo 0600, pasta 0700 em POSIX; no Windows vale a ACL herdada da
pasta de estado). Não decide regra: quem compara é o domínio. Toda leitura que não der um
registro válido do produto pedido vira `ScopeNotApproved(state="invalid")` (falha fechada), sem
repetir o conteúdo do arquivo.
"""

import os
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError, ScopeNotApproved
from harness_dast.domain.run import SLUG_PATTERN
from harness_dast.domain.scope_approval import APPROVE_COMMAND, ScopeApproval

APPROVALS_DIR = "approvals"
MAX_APPROVAL_BYTES = 256 * 1024
_SLUG = re.compile(SLUG_PATTERN)
_DIR_MODE = 0o700
_FILE_MODE = 0o600


def _invalid(product: str) -> ScopeNotApproved:
    return ScopeNotApproved(
        f"O arquivo de aprovação do escopo de {product} está ilegível, é de outra versão do "
        "cálculo ou de outro produto; vale como NÃO aprovado.",
        hint=f"Uma pessoa precisa revisar e aprovar de novo, num terminal: {APPROVE_COMMAND} "
        f"{product}. O agente de IA não aprova.",
        state="invalid",
    )


class FileApprovalStore:
    """Guarda uma aprovação por produto na pasta de estado."""

    def __init__(self, state_dir: Path) -> None:
        """Cria o armazém (nada é criado até o primeiro `write`).

        Args:
            state_dir: Pasta de estado da pessoa usuária.
        """
        self._directory = state_dir / APPROVALS_DIR

    def location(self, product: str) -> Path:
        """Caminho do arquivo de aprovação do produto.

        Raises:
            ConfigError: Se `product` não for um slug (nunca vira caminho fora da pasta).
        """
        if not _SLUG.fullmatch(product):
            raise ConfigError(
                "Nome de produto inválido para a aprovação.",
                hint="Use um slug: minúsculas, dígitos e '-' (ex.: meu-produto).",
            )
        return self._directory / f"{product}.json"

    def read(self, product: str) -> ScopeApproval | None:
        """Lê a aprovação do produto (veja `ApprovalStore.read`)."""
        path = self.location(product)
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_APPROVAL_BYTES + 1)
        except FileNotFoundError:
            return None
        except OSError:
            raise _invalid(product) from None
        if len(raw) > MAX_APPROVAL_BYTES:
            raise _invalid(product)
        try:
            approval = ScopeApproval.model_validate_json(raw)
        except ValidationError:
            raise _invalid(product) from None
        if approval.product != product:
            raise _invalid(product)
        return approval

    def write(self, approval: ScopeApproval) -> None:
        """Grava a aprovação de forma atômica (veja `ApprovalStore.write`)."""
        path = self.location(approval.product)
        temporary = path.with_name(f".{path.name}.tmp")
        data = (approval.model_dump_json(indent=2) + "\n").encode("utf-8")
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            if sys.platform != "win32":
                self._directory.chmod(_DIR_MODE)
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError:
            raise ConfigError(
                "Não foi possível gravar a aprovação do escopo.",
                hint="Confira HDAST_STATE_DIR, o espaço em disco e a permissão de escrita.",
            ) from None
