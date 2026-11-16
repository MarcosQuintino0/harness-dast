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
from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeStore
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.knowledge import KnowledgeProfiles
from harness_dast.application.ports import ApprovalPrompt, ProfileRepository, ZapControl
from harness_dast.application.scope_approval import ApprovedProfileRepository, ScopeApprovals
from harness_dast.application.strategy import StrategyProfiles


def open_approval_store(environ: Mapping[str, str] | None = None) -> FileApprovalStore:
    """Armazém das aprovações na pasta de estado da pessoa usuária (`HDAST_STATE_DIR`)."""
    return FileApprovalStore(default_state_dir(os.environ if environ is None else environ))


def formal_profiles(products_dir: Path) -> ProfileRepository:
    """Perfil aprovado para montar infraestrutura, sem autorizar trabalho no alvo."""
    return ApprovedProfileRepository(FileProfileRepository(products_dir), open_approval_store())


def checked_profiles(products_dir: Path, zap: ZapControl | None = None) -> ProfileRepository:
    """Repositório de perfis que recusa o perfil sem aprovação humana vigente."""
    deps = FileStrategyRepository(products_dir)
    profiles = StrategyProfiles(formal_profiles(products_dir), deps, SystemClock(), zap)
    return KnowledgeProfiles(profiles, FileKnowledgeStore(products_dir), deps, SystemClock(), zap)


def build_scope_approvals(products_dir: Path, prompt: ApprovalPrompt) -> ScopeApprovals:
    """Monta o caso de uso `hdast profile approve|approval` (sem rede)."""
    return ScopeApprovals(
        profiles=FileProfileRepository(products_dir),
        store=open_approval_store(),
        prompt=prompt,
        clock=SystemClock(),
    )
