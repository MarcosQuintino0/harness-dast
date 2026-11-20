"""Leitura do vínculo da pilha e dos arquivos de agora (implementa `StackBindingSource`, ADR 0081).

O que garante: só lê; o hash é do conteúdo bruto, o mesmo que o `stack up` gravou e que o proxy
confere; arquivo ausente, grande demais ou ilegível vira `None`, o que diverge do vínculo (falha
fechada). O que não faz: não valida a aprovação nem o perfil (isso é da cerca) e não escreve.
"""

import hashlib
from pathlib import Path

from harness_dast.adapters.scope_proxy.generate import POLICY_FILE_NAME
from harness_dast.adapters.scope_proxy.policy import MAX_POLICY_BYTES, parse_policy
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.stack_binding import StackDigests

_MAX_SOURCE_BYTES = 1024 * 1024


class FileStackBindingSource:
    """Lê `policy.json` da pilha e o `target.yml` e a aprovação do produto."""

    def __init__(self, products_dir: Path, approvals_dir: Path) -> None:
        """Cria a fonte.

        Args:
            products_dir: Pasta dos produtos (`<produto>/target.yml`).
            approvals_dir: Pasta das aprovações (`<produto>.json`).
        """
        self._products_dir = products_dir
        self._approvals_dir = approvals_dir

    def recorded(self, policy_dir: Path) -> StackDigests | None:
        """Hashes que a política prende; `None` sem vínculo.

        Raises:
            ConfigError: Política ausente, grande demais, ilegível ou inválida.
        """
        path = policy_dir / POLICY_FILE_NAME
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_POLICY_BYTES + 1)
        except OSError:
            raise ConfigError(
                "Não foi possível ler a política da pilha ativa.",
                hint="Recrie a pilha: hdast stack down e depois hdast stack up <produto>.",
            ) from None
        if len(raw) > MAX_POLICY_BYTES:
            raise ConfigError(
                "A política da pilha ativa é grande demais.",
                hint="Recrie a pilha: hdast stack down e depois hdast stack up <produto>.",
            )
        binding = parse_policy(raw).binding
        if binding is None:
            return None
        return StackDigests(
            profile_sha256=binding.profile_sha256, approval_sha256=binding.approval_sha256
        )

    def current(self, product: str) -> StackDigests:
        """Hashes do `target.yml` e da aprovação de agora; `None` no que não pôde ser lido."""
        return StackDigests(
            profile_sha256=_digest(self._products_dir / product / "target.yml"),
            approval_sha256=_digest(self._approvals_dir / f"{product}.json"),
        )


def _digest(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_SOURCE_BYTES + 1)
    except OSError:
        return None
    if len(raw) > _MAX_SOURCE_BYTES:
        return None
    return hashlib.sha256(raw).hexdigest()
