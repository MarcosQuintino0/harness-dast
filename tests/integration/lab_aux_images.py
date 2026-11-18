"""Imagens auxiliares que alguns testes de laboratório usam sem baixar (`--pull=never`).

A prova OAST sobe um cliente Python fixado por digest, e as provas de limpeza esperam a imagem
do Oracle já presente. Numa máquina limpa (GitHub Actions) elas não existem: o workflow pergunta
aqui quais baixar para o pedaço e baixa só essas. A referência do Oracle vem do próprio
`lab/pilot/compose.yaml`, para não haver duas fontes do digest.
"""

import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from tests.integration.oast_support import PYTHON_IMAGE

REPO = Path(__file__).resolve().parents[2]
ORACLE_FILES = frozenset({"test_run_cleanup_oracle.py", "test_cleanup_oracle.py"})
OAST_FILES = frozenset({"test_lab_oast.py"})


def oracle_image(repo: Path = REPO) -> str:
    """Referência fixada por digest do serviço `oracle` da pilha da Clínica."""
    compose = yaml.safe_load((repo / "lab" / "pilot" / "compose.yaml").read_text(encoding="utf-8"))
    return str(compose["services"]["oracle"]["image"])


def auxiliary_images(file_name: str, repo: Path = REPO) -> tuple[str, ...]:
    """Imagens que o arquivo de teste usa sem baixar; vazio quando não há nenhuma."""
    if file_name in OAST_FILES:
        return (PYTHON_IMAGE,)
    if file_name in ORACLE_FILES:
        return (oracle_image(repo),)
    return ()


def main(argv: Sequence[str] | None = None) -> int:
    """Imprime, uma por linha, as imagens auxiliares do arquivo de teste dado."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        sys.stderr.write("Uso: python -m tests.integration.lab_aux_images <arquivo de teste>\n")
        return 2
    sys.stdout.writelines(f"{ref}\n" for ref in auxiliary_images(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
