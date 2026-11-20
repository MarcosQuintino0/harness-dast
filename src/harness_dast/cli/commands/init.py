"""Comando `hdast init`."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import JsonValue

from harness_dast.application.init_from_letter import LetterOutcome, rejection
from harness_dast.application.init_ports import ScaffoldedProduct
from harness_dast.cli.composition import build_init_from_letter, build_init_product
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.domain.errors import ConfigError, ExitCode

_CLEANUP_CREATED = (
    "A pasta cleanup/ foi criada; o script de limpeza é escrito por uma pessoa do time do produto."
)
_CLEANUP_OMITTED = (
    "Sem pasta cleanup/ (a limpeza de dados é opcional). Para tê-la, crie o produto com "
    "hdast init <produto> --with-cleanup."
)


def _render(product: str, result: ScaffoldedProduct) -> str:
    files = "\n".join(f"  - {name}" for name in result.files)
    has_cleanup = any(name.startswith("cleanup/") for name in result.files)
    return (
        f"Produto {product} criado em {result.directory}\n"
        f"Arquivos:\n{files}\n"
        "Próximos passos: preencha o target.yml (escopo, limites e autorização vêm da "
        f"autorização formal) e rode: hdast profile validate {product}\n"
        + (_CLEANUP_CREATED if has_cleanup else _CLEANUP_OMITTED)
    )


def _letter_data(outcome: LetterOutcome, *, check: bool) -> dict[str, JsonValue]:
    data: dict[str, JsonValue] = {
        "product": outcome.product,
        "ready": outcome.ready,
        "check": check,
        "generated_blocks": list(outcome.generated_blocks),
        "issues": [issue.model_dump(mode="json") for issue in outcome.issues],
        "warnings": [warning.model_dump(mode="json") for warning in outcome.warnings],
        "example_data": list(outcome.example_data),
    }
    if outcome.created is not None:
        data["directory"] = outcome.created.directory
        data["files"] = list(outcome.created.files)
    return data


def _render_warnings(outcome: LetterOutcome) -> str:
    if not outcome.warnings:
        return ""
    lines = "\n".join(f"  - {warning.field}: {warning.message}" for warning in outcome.warnings)
    return f"\nAvisos (não bloqueiam; mostre à pessoa e confirme com o dono do produto):\n{lines}"


def _render_letter(outcome: LetterOutcome, *, check: bool) -> str:
    blocks = ", ".join(outcome.generated_blocks)
    if not outcome.ready:
        return f"Carta de {outcome.product}: {len(outcome.issues)} pendência(s); nada foi gerado."
    if check or outcome.created is None:
        return (
            f"Carta de {outcome.product} completa e válida (nada foi criado: --check).\n"
            f"Geraria no target.yml os blocos: {blocks}." + _render_warnings(outcome)
        )
    return (
        f"Produto {outcome.product} criado em {outcome.created.directory} a partir da carta.\n"
        f"Blocos gerados no target.yml (não os edite à mão): {blocks}.\n"
        "Próximo passo: hdast profile validate " + outcome.product + _render_warnings(outcome)
    )


def _init_from_letter(
    ctx: typer.Context,
    product: str,
    letter: Path,
    products_dir: Path | None,
    *,
    check: bool,
    with_cleanup: bool,
) -> int:
    state = get_state(ctx)
    use_case = build_init_from_letter(products_dir)
    if check:
        outcome = use_case.check(product, letter)
    else:
        outcome = use_case.execute(product, letter, with_cleanup=with_cleanup)
    data = _letter_data(outcome, check=check)
    human = _render_letter(outcome, check=check)
    if not outcome.ready:
        error = rejection(outcome)
        emit(build_failure_with_data(error, data), json_mode=state.json_mode, human=human)
        return int(error.exit_code)
    emit(build_success(data), json_mode=state.json_mode, human=human)
    return int(ExitCode.OK)


def init_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug, ex.: meu-produto).")],
    products_dir: Annotated[
        Path | None,
        typer.Option(
            "--products-dir",
            help="Pasta de produtos; sobrepõe HDAST_PRODUCTS_DIR.",
            show_default=False,
        ),
    ] = None,
    with_cleanup: Annotated[
        bool,
        typer.Option(
            "--with-cleanup",
            help="Cria também a pasta cleanup/ (README e exemplo) para o hook de limpeza.",
        ),
    ] = False,
    from_letter: Annotated[
        Path | None,
        typer.Option(
            "--from-letter",
            help="Carta estruturada (carta.yml): gera o target.yml a partir das respostas da "
            "pessoa, sem o agente escrever escopo, limites, autorização nem janelas.",
            show_default=False,
        ),
    ] = None,
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Com --from-letter: só confere a carta e lista campo a campo o que falta; "
            "não cria nada.",
        ),
    ] = False,
) -> int | None:
    """Cria a pasta do produto a partir do modelo, sem sobrescrever nada.

    A pasta cleanup/ só é criada com --with-cleanup: a limpeza de dados é opcional. Com
    --from-letter, o target.yml já nasce com os blocos de proteção gerados da carta.
    """
    if check and from_letter is None:
        raise ConfigError("--check só vale junto de --from-letter.", hint="Informe a carta.")
    if from_letter is not None:
        return _init_from_letter(
            ctx, product, from_letter, products_dir, check=check, with_cleanup=with_cleanup
        )
    state = get_state(ctx)
    result = build_init_product(products_dir).execute(product, with_cleanup=with_cleanup)
    data: dict[str, JsonValue] = {
        "product": product,
        "directory": result.directory,
        "files": list(result.files),
    }
    emit(build_success(data), json_mode=state.json_mode, human=_render(product, result))
    return None
