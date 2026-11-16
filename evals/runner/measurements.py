"""Medicoes versionadas: grava o resumo de uma rodada em `evals/measurements/` e compara duas.

So entram resumos pequenos de laboratorio: `agent-metrics.json`, `score.json`, os `metrics.json`
das execucoes (renomeados por `run_id`) e um `meta.json`. Nunca o transcript, a auditoria do
proxy, o perfil, a pasta `sealed/` nem qualquer arquivo de produto real. Antes de gravar, o texto de
cada arquivo e conferido contra os segredos sorteados da rodada (`sealed/secrets.json`).
"""

import json
import re
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

from evals.runner.cases import REPO_ROOT, EvalError, RoundDirs
from evals.runner.checks_security import _secret_forms
from evals.runner.metrics_models import AgentMetrics
from evals.runner.run_metrics import CLI_STAGES, GapsIn, RunMetricsIn, parse_run_metrics

MEASUREMENTS_DIR = REPO_ROOT / "evals" / "measurements"
LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$")
MIN_SECRET_LENGTH = 8
NO_DATA = "n/d"
TOP_RULES = 10


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def secret_forms(out: Path) -> set[str]:
    """Formas (puro, URL) dos segredos sorteados. Vazio se nao ha `sealed/secrets.json`."""
    values = _read_json(RoundDirs(out).sealed / "secrets.json")
    if not isinstance(values, dict):
        return set()
    return {
        form
        for value in values.values()
        if isinstance(value, str) and len(value) >= MIN_SECRET_LENGTH
        for form in _secret_forms(value)
    }


def ensure_no_secrets(out: Path, texts: dict[str, str]) -> None:
    """Recusa texto que traga algum segredo sorteado da rodada.

    Raises:
        EvalError: Um arquivo contem um segredo; a mensagem cita so o nome do arquivo.
    """
    forms = secret_forms(out)
    leaked = sorted(name for name, text in texts.items() if any(form in text for form in forms))
    if leaked:
        raise EvalError(f"Segredo da rodada encontrado em {leaked}: nada foi gravado.")


def write_agent_metrics(out: Path, metrics: AgentMetrics) -> Path:
    """Grava `<out>/agent-metrics.json`, depois de conferir que nao ha segredo nele.

    Raises:
        EvalError: O texto traz um segredo da rodada.
    """
    text = json.dumps(metrics.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    ensure_no_secrets(out, {"agent-metrics.json": text})
    target = out / "agent-metrics.json"
    target.write_text(text, encoding="utf-8")
    return target


def _round_identity(out: Path) -> tuple[str, str | None]:
    sealed = _read_json(RoundDirs(out).sealed / "mode.json")
    score = _read_json(out / "score.json")
    source = sealed if isinstance(sealed, dict) else score if isinstance(score, dict) else {}
    case = source.get("case")
    if not isinstance(case, str) or not case:
        raise EvalError(f"Nao sei o caso da rodada {out}: falta sealed/mode.json ou score.json.")
    mode = source.get("mode") if isinstance(source.get("mode"), str) else None
    return case, mode


def _hdast_version(out: Path) -> str | None:
    path = RoundDirs(out).workspace / "pyproject.toml"
    try:
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
    except (OSError, ValueError):
        return None
    version = project.get("version")
    return version if isinstance(version, str) else None


def save_measurement(
    out: Path, metrics: AgentMetrics, label: str, day: date, root: Path = MEASUREMENTS_DIR
) -> Path:
    """Copia o resumo da rodada para `<root>/<AAAA-MM-DD>-<caso>-<rotulo>/`.

    Raises:
        EvalError: Rotulo invalido, caso desconhecido, pasta ja existente (nunca sobrescreve) ou
            segredo da rodada em algum arquivo.
    """
    if not LABEL.match(label):
        raise EvalError(f"Rotulo '{label}' invalido: use letras, numeros, '.', '_' e '-'.")
    case, mode = _round_identity(out)
    files = {
        "agent-metrics.json": json.dumps(metrics.model_dump(mode="json"), indent=2) + "\n",
        "meta.json": json.dumps(
            {
                "schema_version": 1,
                "case": case,
                "mode": mode,
                "hdast_version": _hdast_version(out),
                "date": day.isoformat(),
                "label": label,
                "round": out.name,
                "model": metrics.model,
                "pacing": metrics.pacing,
            },
            indent=2,
        )
        + "\n",
    }
    score = out / "score.json"
    if isinstance(_read_json(score), dict):
        files["score.json"] = score.read_text(encoding="utf-8")
    for path in sorted((out / "trace" / "runs").glob("*/metrics.json")):
        if isinstance(_read_json(path), dict):
            files[f"metrics-{path.parent.name}.json"] = path.read_text(encoding="utf-8")
    ensure_no_secrets(out, files)
    folder = root / f"{day.isoformat()}-{case}-{label}"
    if folder.exists():
        raise EvalError(f"{folder} ja existe: escolha outro rotulo (a medicao nao e sobrescrita).")
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def _get(data: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _parsed_runs(runs: list[Any]) -> list[RunMetricsIn]:
    """So as execucoes que o modelo tolerante entende (versao 1); o resto vira "sem dado"."""
    return [parsed for data in runs if (parsed := parse_run_metrics(data)) is not None]


def _sum_known(values: list[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return round(sum(known), 3) if known else None


def _stage_seconds(runs: list[RunMetricsIn], stage: str) -> float | None:
    return _sum_known([run.stages_seconds.get(stage) for run in runs])


def _gaps(runs: list[RunMetricsIn]) -> list[GapsIn]:
    return [run.traffic.gaps for run in runs if run.traffic and run.traffic.gaps]


def _rule_times(runs: list[RunMetricsIn]) -> dict[str, tuple[str | None, float]]:
    """Segundos por regra (`plugin_id`), somados nas execucoes; so regras com `time_ms`."""
    times: dict[str, tuple[str | None, float]] = {}
    for run in runs:
        for rule in run.rules.totals if run.rules else []:
            if rule.time_ms is None:
                continue
            key = str(rule.plugin_id)
            name, seconds = times.get(key, (rule.name, 0.0))
            times[key] = (name or rule.name, seconds + rule.time_ms / 1000)
    return times


def _rule_label(plugin_id: str, name: str | None) -> str:
    return f"regra ZAP {plugin_id} {name} (s)" if name else f"regra ZAP {plugin_id} (s)"


def _load(folder: Path) -> dict[str, Any]:
    if not (folder / "agent-metrics.json").is_file():
        raise EvalError(f"{folder} nao e uma medicao salva: falta agent-metrics.json.")
    return {
        "agent": _read_json(folder / "agent-metrics.json"),
        "score": _read_json(folder / "score.json"),
        "meta": _read_json(folder / "meta.json"),
        "runs": [_read_json(p) for p in sorted(folder.glob("metrics-*.json"))],
    }


def _row(metric: str, a: Any, b: Any) -> dict[str, Any]:
    left, right = _number(a), _number(b)
    diff = round(right - left, 3) if left is not None and right is not None else None
    return {"metric": metric, "a": left, "b": right, "diff": diff}


def _token_rows(prefix: str, a: Any, b: Any) -> list[dict[str, Any]]:
    names = ("input", "output", "cache_creation", "cache_read")
    return [_row(f"{prefix} tokens {name}", _get(a, name), _get(b, name)) for name in names]


def compare_measurements(folder_a: Path, folder_b: Path) -> dict[str, Any]:
    """Diferencas entre duas medicoes salvas. Campo ausente vira `None` (impresso `n/d`), nunca 0.

    Raises:
        EvalError: Uma das pastas nao tem `agent-metrics.json`.
    """
    a, b = _load(folder_a), _load(folder_b)
    ta, tb = _get(a["agent"], "totals"), _get(b["agent"], "totals")
    rows = [
        _row("duracao total (s)", _get(ta, "duration_seconds"), _get(tb, "duration_seconds")),
        *_token_rows("total", _get(ta, "tokens"), _get(tb, "tokens")),
        _row("turnos", _get(ta, "turns"), _get(tb, "turns")),
        _row("chamadas de ferramenta", _get(ta, "tool_calls"), _get(tb, "tool_calls")),
        _row(
            "probe (comandos)",
            _get(ta, "hdast_commands", "probe"),
            _get(tb, "hdast_commands", "probe"),
        ),
        _row("nota", _get(a["score"], "grade"), _get(b["score"], "grade")),
    ]
    for stage in _get(a["agent"], "stages") or {}:
        sa, sb = _get(a["agent"], "stages", stage), _get(b["agent"], "stages", stage)
        rows += [
            _row(f"{stage}: segundos", _get(sa, "seconds"), _get(sb, "seconds")),
            _row(
                f"{stage}: tokens de saida",
                _get(sa, "tokens", "output"),
                _get(sb, "tokens", "output"),
            ),
            _row(f"{stage}: chamadas", _get(sa, "tool_calls"), _get(sb, "tool_calls")),
        ]
    runs_a, runs_b = _parsed_runs(a["runs"]), _parsed_runs(b["runs"])
    rows += [
        _row(
            f"etapa da CLI {stage} (s)",
            _stage_seconds(runs_a, stage),
            _stage_seconds(runs_b, stage),
        )
        for stage in CLI_STAGES
    ]
    gaps_a, gaps_b = _gaps(runs_a), _gaps(runs_b)
    rows.append(
        _row(
            "lacunas do proxy: total (s)",
            _sum_known([g.total_seconds for g in gaps_a]),
            _sum_known([g.total_seconds for g in gaps_b]),
        )
    )
    return {
        "a": str(folder_a.name),
        "b": str(folder_b.name),
        "rows": rows + _rule_rows(_rule_times(runs_a), _rule_times(runs_b)),
    }


def _rule_rows(
    rules_a: dict[str, tuple[str | None, float]], rules_b: dict[str, tuple[str | None, float]]
) -> list[dict[str, Any]]:
    """As `TOP_RULES` regras com maior diferenca de tempo; regra so de um lado fica `n/d`."""
    rows = []
    for plugin_id in {*rules_a, *rules_b}:
        name = (rules_b.get(plugin_id) or rules_a[plugin_id])[0]
        left = rules_a[plugin_id][1] if plugin_id in rules_a else None
        right = rules_b[plugin_id][1] if plugin_id in rules_b else None
        rows.append(_row(_rule_label(plugin_id, name), left, right))
    # Regra que so aparece de um lado nao tem diferenca: pesa pelo tempo que ela tem.
    rows.sort(key=lambda r: (-abs(_weight(r)), r["metric"]))
    return rows[:TOP_RULES]


def _weight(row: dict[str, Any]) -> float:
    if row["diff"] is not None:
        return float(row["diff"])
    return float(row["a"] if row["a"] is not None else row["b"])


def render_comparison(result: dict[str, Any]) -> str:
    """Tabela de texto da comparacao; `n/d` onde falta dado em qualquer lado."""

    def cell(value: float | None) -> str:
        return NO_DATA if value is None else f"{value:.2f}".rstrip("0").rstrip(".")

    lines = [f"A = {result['a']}", f"B = {result['b']}", "", "metrica | A | B | B - A"]
    lines.append("--- | --- | --- | ---")
    lines += [
        f"{r['metric']} | {cell(r['a'])} | {cell(r['b'])} | {cell(r['diff'])}"
        for r in result["rows"]
    ]
    return "\n".join(lines)
