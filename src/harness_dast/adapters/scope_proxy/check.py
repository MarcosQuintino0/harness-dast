"""Verificação de partida: `python -m harness_dast.adapters.scope_proxy.check <politica.json>`.

Usada pelo entrypoint do contêiner antes de subir o mitmproxy. Sai com 0 se a política é
válida e com 3 (código `SCOPE` da CLI) caso contrário, imprimindo uma linha clara em stderr.
"""

import sys
from pathlib import Path

from harness_dast.adapters.scope_proxy.policy import load_policy
from harness_dast.domain.errors import ConfigError, ExitCode


def main(argv: list[str]) -> int:
    """Valida o arquivo de política indicado em `argv[0]`."""
    if len(argv) != 1:
        sys.stderr.write("uso: python -m harness_dast.adapters.scope_proxy.check <politica.json>\n")
        return int(ExitCode.USAGE)
    try:
        policy = load_policy(Path(argv[0]))
    except ConfigError as error:
        sys.stderr.write(f"scope-proxy: RECUSANDO INICIAR. {error.message} {error.hint or ''}\n")
        return int(ExitCode.SCOPE)
    sys.stdout.write(f"scope-proxy: política válida (execução {policy.run_id})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
