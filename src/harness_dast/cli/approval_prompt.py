"""Prompt de terminal da aprovação do escopo, compartilhado por `profile approve` e `setup`.

Mostra o resumo no stderr e exige que a PESSOA digite o nome do produto (ADR 0037). O `setup`
(ADR 0114) acrescenta uma pausa explícita antes do pedido do nome, sem mudar o pedido em si.
"""

import typer

PAUSE_TEXT = "Leia o resumo acima. Para aprovar, continue; para sair sem aprovar, Ctrl+C."


def confirm_product_name(product: str) -> bool:
    """Pede que a pessoa digite o nome do produto; `True` só se for exatamente ele."""
    answer = typer.prompt(
        f"Digite '{product}' para aprovar (outra coisa cancela)",
        default="",
        show_default=False,
        err=True,
    )
    return str(answer).strip() == product


def _pause() -> bool:
    typer.echo(PAUSE_TEXT, err=True)
    try:
        typer.prompt("Enter para continuar", default="", show_default=False, err=True)
    except typer.Abort:
        return False
    return True


class TerminalApprovalPrompt:
    """Mostra o resumo no stderr e exige que a pessoa digite o nome do produto."""

    def __init__(self, *, pause: bool = False) -> None:
        """Cria o prompt.

        Args:
            pause: Se `True`, faz a pausa "leia o resumo" antes do pedido do nome (`setup`);
                Ctrl+C nela sai sem aprovar.
        """
        self._pause = pause

    def confirm(self, product: str, summary: tuple[str, ...], changes: tuple[str, ...]) -> bool:
        """Devolve `True` só se o texto digitado for exatamente o nome do produto."""
        typer.echo(f"Escopo de {product} que você vai APROVAR:", err=True)
        for line in summary:
            typer.echo(f"  {line}", err=True)
        if changes:
            typer.echo("Mudou desde a aprovação anterior:", err=True)
            for change in changes:
                typer.echo(f"  - {change}", err=True)
        typer.echo(
            "Confira com a carta de autorização. Depois da aprovação, qualquer mudança nestes "
            "blocos do perfil exige nova aprovação sua.",
            err=True,
        )
        if self._pause and not _pause():
            return False
        return confirm_product_name(product)
