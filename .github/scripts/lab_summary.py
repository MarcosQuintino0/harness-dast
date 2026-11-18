"""Junta os resultados dos pedaços do laboratório e escreve o resumo da rodada.

Uso: `python lab_summary.py --artefatos PASTA --pedacos pedacos.json [--saida ARQUIVO]`

Cada pedaço planejado deve ter a pasta `lab-<nome>` com o `junit.xml` e, se houver, os
diagnósticos da vigia em `vigia/*.jsonl`. Pedaço sem JUnit conta como falha, porque a
máquina pode ter caído antes de o pytest escrever o resultado. A saída é 1 se houver
falha, erro, pedaço sem resultado ou nenhum teste aprovado.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

SLOWEST = 15
ARTIFACT_PREFIX = "lab-"


@dataclass
class PieceResult:
    """O que um pedaço devolveu: contagens, tempos por teste e registros da vigia."""

    name: str
    counts: Counter[str] = field(default_factory=Counter)
    timings: list[tuple[float, str]] = field(default_factory=list)
    seconds: float = 0.0
    watch: list[str] = field(default_factory=list)
    has_junit: bool = False


def _status(case: ET.Element) -> str:
    if case.find("failure") is not None or case.find("error") is not None:
        return "failed"
    return "skipped" if case.find("skipped") is not None else "passed"


def _read_junit(path: Path, result: PieceResult) -> None:
    try:
        root = ET.parse(path).getroot()  # noqa: S314 - o JUnit é produzido pelo próprio pytest.
    except (ET.ParseError, OSError):
        return
    result.has_junit = True
    for case in root.iter("testcase"):
        result.counts[_status(case)] += 1
        seconds = float(case.get("time") or 0)
        result.seconds += seconds
        name = ".".join(filter(None, (case.get("classname"), case.get("name"))))
        result.timings.append((seconds, name))


def _read_watch(directory: Path, result: PieceResult) -> None:
    records = 0
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            records += 1
            try:
                watch = json.loads(line)
                categories = ", ".join(watch.get("categories", []))
                detail = categories or (watch.get("status") if watch.get("status") != "ok" else "")
                if detail:
                    result.watch.append(f"{watch.get('stack_run_id', '?')}|{detail}")
            except (ValueError, AttributeError, TypeError):
                result.watch.append(f"?|registro ilegível em {path.name}")
    result.counts["watch_records"] = records


def load_piece(artifacts: Path, name: str) -> PieceResult:
    """Lê o JUnit e a vigia de um pedaço; sem JUnit, `has_junit` fica falso."""
    result = PieceResult(name)
    directory = artifacts / f"{ARTIFACT_PREFIX}{name}"
    if directory.is_dir():
        _read_junit(directory / "junit.xml", result)
        _read_watch(directory / "vigia", result)
    return result


def _piece_status(result: PieceResult) -> str:
    if not result.has_junit:
        return "sem resultado"
    if result.counts["failed"]:
        return "falhou"
    return "ok" if result.counts["passed"] else "só pulados"


def render(results: list[PieceResult]) -> tuple[str, bool]:
    """Monta o Markdown do resumo e diz se a rodada falhou."""
    total: Counter[str] = Counter()
    for result in results:
        total.update(result.counts)
    missing = [r.name for r in results if not r.has_junit]
    failed = bool(total["failed"] or missing or not total["passed"])
    lines = [
        "## Laboratório",
        "",
        f"{total['passed']} aprovados · {total['failed']} falharam · {total['skipped']} pulados "
        f"· {len(results)} pedaços",
        "",
    ]
    if missing:
        lines += ["### Pedaços sem resultado (contam como falha)", ""]
        lines += [f"- <code>{escape(name)}</code>" for name in missing]
        lines.append("")
    lines += [
        "### Tempo por pedaço",
        "",
        "| Pedaço | Situação | Testes | Tempo |",
        "| --- | --- | ---: | ---: |",
    ]
    for result in sorted(results, key=lambda r: r.seconds, reverse=True):
        tests = result.counts["passed"] + result.counts["failed"] + result.counts["skipped"]
        lines.append(
            f"| <code>{escape(result.name)}</code> | {_piece_status(result)} | {tests} "
            f"| {result.seconds:.0f} s |"
        )
    timings = sorted((t for r in results for t in r.timings), reverse=True)[:SLOWEST]
    lines += ["", f"### Até {SLOWEST} testes mais lentos", ""]
    lines += [f"- {seconds:.2f} s · <code>{escape(name)}</code>" for seconds, name in timings]
    if not timings:
        lines.append("Nenhum JUnit trouxe resultados de teste.")
    lines += ["", "### Vigia do proxy", ""]
    watched = [(r.name, entry) for r in results for entry in r.watch]
    for piece, entry in watched:
        stack, _, detail = entry.partition("|")
        lines.append(
            f"- <code>{escape(piece)}</code> · pilha <code>{escape(stack)}</code> "
            f"· <code>{escape(detail)}</code>"
        )
    records = sum(r.counts["watch_records"] for r in results)
    lines.append(f"{records} registros da vigia coletados, {len(watched)} com trava ou aviso.")
    return "\n".join(lines) + "\n", failed


def main(argv: list[str] | None = None) -> int:
    """Lê os pedaços planejados, escreve o resumo e devolve 1 se a rodada falhou."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artefatos", type=Path, required=True)
    parser.add_argument("--pedacos", type=Path, required=True)
    parser.add_argument("--saida", type=Path)
    args = parser.parse_args(argv)
    try:
        planned = json.loads(args.pedacos.read_text(encoding="utf-8"))
        names = [str(piece["name"]) for piece in planned]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.write(f"Lista de pedaços ilegível em {args.pedacos}. {exc}\n")
        return 2
    report, failed = render([load_piece(args.artefatos, name) for name in names])
    if args.saida is None:
        sys.stdout.write(report)
    else:
        with args.saida.open("a", encoding="utf-8") as stream:
            stream.write(report)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
