"""Montagem da aprovação humana do escopo (ADR 0037).

`checked_profiles` é o repositório que TODO comando que toca o alvo recebe: só devolve o perfil
se uma pessoa aprovou os blocos de proteção e eles não mudaram. O repositório comum
(`FileProfileRepository`) fica só para comandos de leitura (`profile validate`, `doctor`,
`spec inspect`, `report`, `panel`, `secret list`).
"""

import os
from collections.abc import Mapping
from pathlib import Path

from harness_dast.adapters.storage.approval_store import FileApprovalStore
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.ports import ApprovalPrompt, ProfileRepository
from harness_dast.application.scope_approval import ApprovedProfileRepository, ScopeApprovals
from harness_dast.application.strategy import StrategyProfiles


def open_approval_store(environ: Mapping[str, str] | None = None) -> FileApprovalStore:
    """Armazém das aprovações na pasta de estado da pessoa usuária (`HDAST_STATE_DIR`)."""
    return FileApprovalStore(default_state_dir(os.environ if environ is None else environ))


def checked_profiles(products_dir: Path) -> ProfileRepository:
    """Repositório de perfis que recusa o perfil sem aprovação humana vigente."""
    approved = ApprovedProfileRepository(FileProfileRepository(products_dir), open_approval_store())
    return StrategyProfiles(approved, FileStrategyRepository(products_dir), SystemClock())


def build_scope_approvals(products_dir: Path, prompt: ApprovalPrompt) -> ScopeApprovals:
    """Monta o caso de uso `hdast profile approve|approval` (sem rede)."""
    return ScopeApprovals(
        profiles=FileProfileRepository(products_dir),
        store=open_approval_store(),
        prompt=prompt,
        clock=SystemClock(),
    )
