"""Falsos da aprovação humana do escopo (ADR 0037).

- `InMemoryApprovalStore` e `ScriptedApprovalPrompt` para testes de caso de uso;
- `approve_product_on_disk`: o que uma PESSOA faria no terminal, para os testes de contrato que
  rodam a CLI inteira sobre uma pasta de produtos real (a pasta de estado vem de
  `HDAST_STATE_DIR`, que `tests/conftest.py` já isola por teste).
"""

import os
from datetime import UTC, datetime
from pathlib import Path

from harness_dast.adapters.storage.approval_store import FileApprovalStore
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.domain.errors import ConfigError, ScopeNotApproved
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_approval import ScopeApproval, create_approval
from harness_dast.domain.scope_approval_summary import describe_protection

APPROVED_AT = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


class InMemoryApprovalStore:
    """`ApprovalStore` falso: dicionário `produto -> aprovação`, com leitura inválida opcional."""

    def __init__(self) -> None:
        self.items: dict[str, ScopeApproval] = {}
        self.invalid: set[str] = set()
        self.fail_writes = False

    def read(self, product: str) -> ScopeApproval | None:
        if product in self.invalid:
            raise ScopeNotApproved("aprovação ilegível", state="invalid")
        return self.items.get(product)

    def write(self, approval: ScopeApproval) -> None:
        if self.fail_writes:
            raise ConfigError("falha de gravação injetada")
        self.invalid.discard(approval.product)  # gravar substitui o arquivo ruim
        self.items[approval.product] = approval


class ScriptedApprovalPrompt:
    """`ApprovalPrompt` falso: responde o que o teste mandou e guarda o que foi mostrado."""

    def __init__(self, answer: bool = True) -> None:
        self.answer = answer
        self.shown: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []

    def confirm(self, product: str, summary: tuple[str, ...], changes: tuple[str, ...]) -> bool:
        self.shown.append((product, summary, changes))
        return self.answer


def approval_for(profile: ProductProfile) -> ScopeApproval:
    """A aprovação que uma pessoa gravaria para este perfil, agora."""
    return create_approval(profile, APPROVED_AT, describe_protection(profile))


def approve_profile(store: InMemoryApprovalStore, profile: ProductProfile) -> ScopeApproval:
    """Grava no armazém falso a aprovação do perfil e a devolve."""
    approval = approval_for(profile)
    store.write(approval)
    return approval


def approve_product_on_disk(products_dir: Path, product: str) -> ScopeApproval:
    """Grava a aprovação do `target.yml` em disco, na pasta de estado do teste."""
    profile = FileProfileRepository(products_dir).load(product)
    approval = approval_for(profile)
    FileApprovalStore(default_state_dir(os.environ)).write(approval)
    return approval
