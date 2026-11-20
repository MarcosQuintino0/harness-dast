"""Junta os resultados dos pedaços do laboratório e escreve o resumo da rodada.

Dois usos:

- `python lab_summary.py --gravar-estado ARQUIVO --nome N --status S --junit J`, no fim de cada
  pedaço: grava o `estado.json` com o status do job e as contagens do JUnit.
- `python lab_summary.py --artefatos PASTA --pedacos pedacos.json [--saida ARQUIVO]
  [--resultado-pedaco R]`, no job de resumo.

Cada pedaço planejado deve ter a pasta `lab-<nome>` com `junit.xml` e `estado.json`. É falha
o pedaço sem artefato, sem JUnit, sem estado, com job diferente de `success` ou sem nenhum
teste aprovado (mesmo que tenha só pulados). O resultado do job `pedaco` também conta. A saída
é 1 se houver falha.
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
    """O que um pedaço devolveu: contagens, tempos por teste, estado do job e vigia."""

    name: str
    counts: Counter[str] = field(default_factory=Counter)
    timings: list[tuple[float, str]] = field(default_factory=list)
    seconds: float = 0.0
    watch: list[str] = field(default_factory=list)
    has_artifact: bool = False
    has_junit: bool = False
    job_status: str | None = None

    @property
    def reasons(self) -> list[str]:
        """Motivos pelos quais o pedaço conta como falha; vazio quando está ok."""
        if not self.has_artifact:
            return ["sem artefato"]
        if not self.has_junit:
            return ["sem junit"]
        reasons = []
        if self.job_status is None:
            reasons.append("sem estado.json")
        elif self.job_status != "success":
            reasons.append(f"job terminou como {self.job_status}")
        if self.counts["failed"]:
            reasons.append(f"{self.counts['failed']} testes falharam")
        if not self.counts["passed"]:
            reasons.append(f"nenhum teste aprovado ({self.counts['skipped']} pulados)")
        return reasons


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


def _read_state(path: Path, result: PieceResult) -> None:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        result.job_status = str(state["status"])
    except (OSError, ValueError, KeyError, TypeError):
        result.job_status = None


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
    """Lê o JUnit, o estado e a vigia de um pedaço."""
    result = PieceResult(name)
    directory = artifacts / f"{ARTIFACT_PREFIX}{name}"
    if directory.is_dir():
        result.has_artifact = True
        _read_junit(directory / "junit.xml", result)
        _read_state(directory / "estado.json", result)
        _read_watch(directory / "vigia", result)
    return result


def write_state(path: Path, name: str, status: str, junit: Path) -> None:
    """Grava o `estado.json` do pedaço com o status do job e as contagens do JUnit."""
    result = PieceResult(name)
    _read_junit(junit, result)
    state = {
        "nome": name,
        "status": status,
        "passed": result.counts["passed"],
        "failed": result.counts["failed"],
        "skipped": result.counts["skipped"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def render(results: list[PieceResult], job_result: str | None = None) -> tuple[str, bool]:
    """Monta o Markdown do resumo e diz se a rodada falhou."""
    total: Counter[str] = Counter()
    for result in results:
        total.update(result.counts)
    bad = [(r.name, r.reasons) for r in results if r.reasons]
    job_bad = job_result not in (None, "success")
    lines = [
        "## Laboratório",
        "",
        f"{total['passed']} aprovados · {total['failed']} falharam · {total['skipped']} pulados "
        f"· {len(results)} pedaços",
        "",
    ]
    if job_bad:
        lines += [f"O job dos pedaços terminou como <code>{escape(str(job_result))}</code>.", ""]
    if bad:
        lines += ["### Pedaços com falha", ""]
        lines += [f"- <code>{escape(n)}</code>: {escape('; '.join(why))}" for n, why in bad]
        lines.append("")
    lines += [
        "### Tempo por pedaço",
        "",
        "| Pedaço | Situação | Testes | Tempo |",
        "| --- | --- | ---: | ---: |",
    ]
    for result in sorted(results, key=lambda r: r.seconds, reverse=True):
        tests = result.counts["passed"] + result.counts["failed"] + result.counts["skipped"]
        situation = escape("; ".join(result.reasons)) or "ok"
        name = escape(result.name)
        lines.append(f"| <code>{name}</code> | {situation} | {tests} | {result.seconds:.0f} s |")
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
    return "\n".join(lines) + "\n", bool(bad or job_bad or not results)


def main(argv: list[str] | None = None) -> int:
    """Grava o estado de um pedaço ou escreve o resumo; devolve 1 se a rodada falhou."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artefatos", type=Path)
    parser.add_argument("--pedacos", type=Path)
    parser.add_argument("--saida", type=Path)
    parser.add_argument("--resultado-pedaco")
    parser.add_argument("--gravar-estado", type=Path)
    parser.add_argument("--nome")
    parser.add_argument("--status")
    parser.add_argument("--junit", type=Path)
    args = parser.parse_args(argv)
    if args.gravar_estado is not None:
        if not (args.nome and args.status and args.junit):
            sys.stderr.write("--gravar-estado exige --nome, --status e --junit.\n")
            return 2
        write_state(args.gravar_estado, args.nome, args.status, args.junit)
        return 0
    if args.artefatos is None or args.pedacos is None:
        sys.stderr.write("Informe --artefatos e --pedacos, ou --gravar-estado.\n")
        return 2
    try:
        planned = json.loads(args.pedacos.read_text(encoding="utf-8"))
        names = [str(piece["name"]) for piece in planned]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.write(f"Lista de pedaços ilegível em {args.pedacos}. {exc}\n")
        return 2
    results = [load_piece(args.artefatos, name) for name in names]
    report, failed = render(results, args.resultado_pedaco)
    if args.saida is None:
        sys.stdout.write(report)
    else:
        with args.saida.open("a", encoding="utf-8") as stream:
            stream.write(report)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
