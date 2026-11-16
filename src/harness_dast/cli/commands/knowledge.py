"""Comandos de captura e inspeção local do conhecimento."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeStore
from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.knowledge_capture import CaptureKnowledge
from harness_dast.application.strategy import _context
from harness_dast.cli.approval_composition import formal_profiles, open_approval_store
from harness_dast.cli.composition import build_spec_loader, products_dir_or_default
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.stack_lock_composition import hold_stack
from harness_dast.cli.strategy_composition import open_capture_zap
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge import Knowledge

_DIR = typer.Option("--products-dir", show_default=False)


def validate_command(
    ctx: typer.Context, product: str, products_dir: Annotated[Path | None, _DIR] = None
) -> None:
    """Compara dependências locais; sem motor, a reutilização exige revisão."""
    root = products_dir_or_default(products_dir)
    profile = FileProfileRepository(root).load(product)
    raw = FileKnowledgeStore(root).read(product)
    if raw is None:
        raise ConfigError("knowledge.yml ausente.")
    knowledge = Knowledge.from_data(raw)
    deps = FileStrategyRepository(root)
    deps.check_references(product, knowledge.references)
    current, _ = _context(deps, product, profile)
    reasons = knowledge.review(current, SystemClock().now())
    data: dict[str, JsonValue] = {
        "product": product,
        "entries": [
            {"kind": e.kind, "reasons": list(r)}
            for e, r in zip(knowledge.entries, reasons, strict=True)
        ],
        "reusable": not any(
            r for e, r in zip(knowledge.entries, reasons, strict=True) if e.kind != "effect"
        ),
        "classification": "proposed" if any(reasons) else "automatic",
        "engine_status": "unavailable",
    }
    emit(build_success(data), json_mode=get_state(ctx).json_mode, human=str(data))


def capture_command(
    ctx: typer.Context, product: str, products_dir: Annotated[Path | None, _DIR] = None
) -> None:
    """Captura referências e vínculo do motor, sem alcançar o alvo."""
    root = products_dir_or_default(products_dir)
    with hold_stack("knowledge capture", product):
        zap, control = open_capture_zap(product, products_dir, get_state(ctx).secrets)
        try:
            service = CaptureKnowledge(
                formal_profiles(root),
                FileKnowledgeStore(root),
                FileStrategyRepository(root),
                open_approval_store(),
                SystemClock(),
                FileProductDocuments(root),
                build_spec_loader(root),
                zap,
                control,
            )
            data = service.execute(product)
        finally:
            zap.close()
    emit(build_success(data), json_mode=get_state(ctx).json_mode, human=str(data))


def build_knowledge_app() -> typer.Typer:
    """Monta comandos de conhecimento."""
    app = typer.Typer(help="Conhecimento de produto sem ampliação de autoridade.")
    app.command("validate")(validate_command)
    app.command("diff")(validate_command)
    app.command("capture")(capture_command)
    return app
