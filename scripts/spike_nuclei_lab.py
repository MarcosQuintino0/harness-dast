"""Spike do Nuclei (nunca na main): aciona a CLI do hdast como o suporte de integracao do laboratorio.

Usa `tests.integration.lab_support.LabCli`: pastas isoladas em `--root`, aprovacao descartavel do escopo
(o que o suporte de integracao faz no lugar da pessoa; nao e `profile approve`) e pilha com sufixo `-claude`.
Subcomandos: `install NOME PASTA [ARQ...]` e `hdast ARGS...` (chama `python -m harness_dast --json ARGS`).
"""

import json
import os
import sys
from pathlib import Path

from tests.integration.lab_support import LabCli

VAMPI_ENV = {
    "VAMPI_USER_A_USERNAME": "name1",
    "VAMPI_USER_A_PASSWORD": "pass1",
    "VAMPI_USER_B_USERNAME": "name2",
    "VAMPI_USER_B_PASSWORD": "pass2",
    "VAMPI_ADMIN_USERNAME": "admin",
    "VAMPI_ADMIN_PASSWORD": "pass1",
}


def main(argv: list[str]) -> int:
    root = Path(os.environ["SPIKE_ROOT"])
    os.environ.setdefault("HDAST_IT_STACK_SUFFIX", "-claude")
    cli = LabCli(root, {**VAMPI_ENV, "HDAST_STACK_BUILD": os.environ.get("HDAST_STACK_BUILD", "0")})
    if argv[0] == "install":
        cli.install_product(argv[1], Path(argv[2]), tuple(Path(p) for p in argv[3:]))
        return 0
    timeout = int(os.environ.get("SPIKE_TIMEOUT", "1800"))
    result = cli.run(*argv[1:], timeout=timeout)
    print(json.dumps({"code": result.code, "envelope": result.envelope}, ensure_ascii=False)[:6000])
    print(result.stderr[-1500:], file=sys.stderr)
    return result.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
