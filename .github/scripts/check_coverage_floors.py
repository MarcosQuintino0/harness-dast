"""Verifica pisos de cobertura de ramos por camada a partir do `coverage.json`.

Uso: `python check_coverage_floors.py coverage.json caminho/da/camada=PISO ...`

O caminho é relativo ao diretório atual (a raiz do repositório, como no CI). Regras:

- camada abaixo do piso: falha (saída 1);
- prefixo cujo diretório não existe: falha (erro de digitação não pode passar em silêncio);
- diretório que só tem `__init__.py` (camada legitimamente vazia): ignorado com aviso, para
  o piso passar a valer sozinho quando houver código;
- diretório com código mas nada medido no `coverage.json` (por exemplo `source` quebrado):
  falha, porque seria um gate vazio.
"""

import json
import sys
from pathlib import Path


def layer_coverage(report: dict[str, dict[str, dict[str, float]]], prefix: str) -> float | None:
    """Calcula a cobertura combinada de linhas e ramos de uma camada.

    Args:
        report: Conteúdo do `coverage.json`.
        prefix: Prefixo de caminho da camada (separador `/`).

    Returns:
        Percentual de 0 a 100, ou `None` se a camada não tem instruções medidas.
    """
    statements = covered = 0.0
    for name, data in report["files"].items():
        if not name.replace("\\", "/").startswith(prefix.rstrip("/") + "/"):
            continue
        summary = data["summary"]
        statements += summary["num_statements"] + summary.get("num_branches", 0)
        covered += summary["covered_lines"] + summary.get("covered_branches", 0)
    if statements == 0:
        return None
    return 100.0 * covered / statements


def _has_code(directory: Path) -> bool:
    return any(path.name != "__init__.py" for path in directory.rglob("*.py"))


def main(argv: list[str]) -> int:
    """Executa a verificação.

    Args:
        argv: Caminho do `coverage.json` seguido de pares `camada=piso`.

    Returns:
        0 se todos os pisos foram cumpridos, 1 caso contrário.
    """
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    failed = False
    for pair in argv[1:]:
        prefix, _, floor_text = pair.partition("=")
        floor = float(floor_text)
        directory = Path(prefix)
        if not directory.is_dir():
            sys.stdout.write(f"{prefix}: diretório não existe; confira o prefixo ERRO\n")
            failed = True
            continue
        value = layer_coverage(report, prefix)
        if value is None:
            if _has_code(directory):
                sys.stdout.write(f"{prefix}: tem código, mas nada foi medido ERRO\n")
                failed = True
            else:
                sys.stdout.write(f"{prefix}: sem código medido, piso ignorado\n")
            continue
        status = "ok" if value >= floor else "ABAIXO DO PISO"
        sys.stdout.write(f"{prefix}: {value:.1f}% (piso {floor:.0f}%) {status}\n")
        failed = failed or value < floor
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
