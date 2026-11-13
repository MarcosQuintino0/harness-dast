"""Linha de comando: `uv run python -m evals.runner <subcomando>`."""

import argparse
import json
import sys
from pathlib import Path

from evals.runner import gitutil, scoring
from evals.runner.cases import EvalError, RoundDirs
from evals.runner.collect import collect
from evals.runner.prepare import MODES, prepare
from evals.runner.render import failures, render_classify, render_score


def build_parser() -> argparse.ArgumentParser:
    """Parser com os subcomandos `prepare`, `collect`, `snapshot`, `score` e `classify`."""
    parser = argparse.ArgumentParser(prog="python -m evals.runner", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="cria o workspace cego e lacra o modo")
    prep.add_argument("--case", required=True)
    prep.add_argument("--mode", choices=MODES, default="random")
    prep.add_argument("--seed", type=int, default=0)
    prep.add_argument("--out", type=Path, required=True)
    prep.add_argument("--allow-leaks", action="store_true")
    coll = sub.add_parser("collect", help="junta o rastro em <out>/trace")
    coll.add_argument("--out", type=Path, required=True)
    coll.add_argument("--state-dir", type=Path, default=None)
    snap = sub.add_parser("snapshot", help="instantaneo do perfil durante a rodada")
    snap.add_argument("--out", type=Path, required=True)
    snap.add_argument("--label", default="manual")
    score = sub.add_parser("score", help="nota em <out>/score.json e score.md")
    score.add_argument("--out", type=Path, required=True)
    score.add_argument("--tokens", type=int, default=None)
    score.add_argument("--duration-seconds", type=int, default=None)
    classify = sub.add_parser("classify", help="modelo de classificacao das falhas")
    classify.add_argument("--out", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> str:
    out: Path = args.out
    if args.command == "prepare":
        result = prepare(args.case, args.mode, args.seed, out, allow_leaks=args.allow_leaks)
        return (
            f"workspace: {result.workspace}\nlacre (NAO mostrar ao agente): {result.sealed}\n"
            f"exclusoes: {len(result.excluded)}; termos do gabarito na copia: {len(result.leaks)}"
        )
    if args.command == "collect":
        collected = collect(out, state_dir=args.state_dir)
        return f"rastro: {collected.trace}; problemas: {list(collected.problems) or 'nenhum'}"
    if args.command == "snapshot":
        return f"instantaneo: {gitutil.snapshot(RoundDirs(out).workspace, args.label)}"
    result_json = scoring.compute(
        out, scoring.Cost(getattr(args, "tokens", None), getattr(args, "duration_seconds", None))
    )
    if args.command == "score":
        (out / "score.json").write_text(json.dumps(result_json, indent=2), encoding="utf-8")
        (out / "score.md").write_text(render_score(result_json), encoding="utf-8")
        return f"nota {result_json['grade']} de 10 (score.json e score.md em {out})"
    (out / "classify.md").write_text(render_classify(result_json), encoding="utf-8")
    return f"{len(failures(result_json))} falha(s) para classificar em {out / 'classify.md'}"


def main(argv: list[str] | None = None) -> int:
    """Executa o subcomando. Devolve 0 em sucesso e 2 em erro de uso."""
    args = build_parser().parse_args(argv)
    try:
        message = _run(args)
    except EvalError as error:
        sys.stderr.write(f"erro: {error}\n")
        return 2
    sys.stdout.write(message + "\n")
    return 0
