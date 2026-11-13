"""Busca, na copia entregue ao agente, de termos que revelam as falhas plantadas."""

import re
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class LeakHit:
    """Um termo do gabarito encontrado em um arquivo da copia."""

    path: str
    term: str
    line: int


def scan_leaks(root: Path, terms: tuple[str, ...]) -> list[LeakHit]:
    """Procura cada termo (sem diferenciar maiusculas) em todo arquivo de texto de `root`."""
    patterns = [
        (term, re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)) for term in terms
    ]
    hits: list[LeakHit] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.relative_to(root).parts:
            continue
        if path.stat().st_size > MAX_BYTES:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(lines, start=1):
            hits.extend(LeakHit(rel, term, number) for term, pat in patterns if pat.search(line))
    return hits
