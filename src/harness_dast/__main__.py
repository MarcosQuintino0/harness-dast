"""Ponto de entrada de `hdast` e `python -m harness_dast`."""

import sys


def main() -> int:
    """Consulta a versão sem carregar as dependências dos demais comandos."""
    if sys.argv[1:] == ["--version"]:
        from harness_dast.cli.commands.version import emit_version

        emit_version(json_mode=False, plain=True)
        return 0

    from harness_dast.cli.app import main as run_cli

    return run_cli()


if __name__ == "__main__":
    sys.exit(main())
