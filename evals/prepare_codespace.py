"""Prepara a cópia e o lacre da rodada cega em um Codespace descartável.

A subida da pilha cabe ao agente avaliado após a aprovação do coordenador.
"""

import argparse
import sys
from pathlib import Path

from evals.runner.cases import CASES_DIR, REPO_ROOT, EvalError
from evals.runner.prepare import MODES, PrepareResult, prepare


def prepare_codespace(
    case: str,
    mode: str,
    seed: int,
    out: Path,
    *,
    source: Path = REPO_ROOT,
    cases_dir: Path = CASES_DIR,
) -> PrepareResult:
    """Prepara a cópia fora do checkout e mantém a base do Git no lacre."""
    out = out.resolve()
    if out.is_relative_to(source.resolve()):
        raise EvalError("Use uma pasta de saída fora do checkout do coordenador.")
    if case not in {path.parent.name for path in cases_dir.glob("*/case.yml")}:
        raise EvalError("Escolha um caso versionado em evals/cases/.")
    return prepare(case, mode, seed, out, source=source, cases_dir=cases_dir, separate_git=True)


def main(argv: list[str] | None = None) -> int:
    """Recebe os parâmetros da rodada e informa o caminho da cópia cega."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="nome do caso em evals/cases/")
    parser.add_argument("--mode", choices=MODES, default="random")
    parser.add_argument("--seed", type=int, required=True, help="semente da rodada")
    parser.add_argument("--out", type=Path, required=True, help="pasta nova fora do checkout")
    args = parser.parse_args(argv)
    try:
        result = prepare_codespace(args.case, args.mode, args.seed, args.out)
    except (EvalError, OSError) as error:
        sys.stderr.write(f"Erro ao preparar a cópia: {error}\n")
        return 2
    sys.stdout.write(f"Cópia cega: {result.workspace}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
