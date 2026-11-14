"""Medicoes salvas e comparacao entre duas."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from evals.runner.cases import EvalError
from evals.runner.cli import main
from evals.runner.measurements import (
    compare_measurements,
    render_comparison,
    save_measurement,
    write_agent_metrics,
)
from evals.runner.metrics import measure_agent
from tests.unit.evals.support import make_round, write, write_json
from tests.unit.evals.test_metrics import Builder, standard_round

DAY = date(2026, 11, 14)


def round_with_transcript(repo: Path, out: Path, builder: Builder | None = None) -> None:
    make_round(repo, out)
    (builder or standard_round()).save(out)


def test_save_copies_only_the_summary_files(repo: Path, out: Path, tmp_path: Path) -> None:
    round_with_transcript(repo, out)
    write_json(out / "score.json", {"case": "mini", "grade": 8.5})
    write_json(out / "trace" / "runs" / "run-1" / "metrics.json", {"schema_version": 1})
    write(out / "trace" / "runs" / "run-1" / "audit.jsonl", "{}")
    write(out / "workspace" / "products" / "mini" / "target.yml", "perfil")
    root = tmp_path / "measurements"

    folder = save_measurement(out, measure_agent(out), "v1-1", DAY, root=root)

    assert folder == root / "2026-11-14-mini-v1-1"
    assert sorted(p.name for p in folder.iterdir()) == [
        "agent-metrics.json",
        "meta.json",
        "metrics-run-1.json",
        "score.json",
    ]


def test_meta_records_case_mode_version_date_label_and_model(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    round_with_transcript(repo, out)
    write(out / "workspace" / "pyproject.toml", '[project]\nname = "x"\nversion = "1.2.3"\n')

    folder = save_measurement(out, measure_agent(out), "v1-1", DAY, root=tmp_path / "m")

    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["case"] == "mini"
    assert meta["mode"] == "vulnerable"
    assert meta["hdast_version"] == "1.2.3"
    assert meta["date"] == "2026-11-14"
    assert meta["label"] == "v1-1"
    assert meta["model"] == "claude-test"


def test_meta_version_is_null_when_the_workspace_has_no_pyproject(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    round_with_transcript(repo, out)

    folder = save_measurement(out, measure_agent(out), "x", DAY, root=tmp_path / "m")

    assert json.loads((folder / "meta.json").read_text(encoding="utf-8"))["hdast_version"] is None


def test_save_never_overwrites_an_existing_folder(repo: Path, out: Path, tmp_path: Path) -> None:
    round_with_transcript(repo, out)
    metrics = measure_agent(out)
    save_measurement(out, metrics, "v1-1", DAY, root=tmp_path / "m")

    with pytest.raises(EvalError, match="ja existe"):
        save_measurement(out, metrics, "v1-1", DAY, root=tmp_path / "m")


@pytest.mark.parametrize("label", ["", "../fora", "a b", "-x", "a/b"])
def test_save_rejects_a_label_that_is_not_a_plain_name(
    repo: Path, out: Path, tmp_path: Path, label: str
) -> None:
    round_with_transcript(repo, out)

    with pytest.raises(EvalError, match="invalido"):
        save_measurement(out, measure_agent(out), label, DAY, root=tmp_path / "m")


def test_save_refuses_when_a_round_secret_is_in_a_file(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    round_with_transcript(repo, out)
    secret = next(
        v for v in json.loads((out / "sealed" / "secrets.json").read_text()).values() if len(v) >= 8
    )
    write_json(out / "score.json", {"case": "mini", "detail": f"senha {secret}"})
    root = tmp_path / "m"

    with pytest.raises(EvalError, match="Segredo"):
        save_measurement(out, measure_agent(out), "v", DAY, root=root)

    assert not root.exists()


def test_agent_metrics_with_a_secret_is_not_written(repo: Path, out: Path) -> None:
    secret = "lab_0123456789abcdef"  # noqa: S105 - valor de teste
    builder = Builder()
    builder.call(f"uv run hdast probe mini --{secret}")
    builder.call(f"uv run hdast probe mini --{secret}")
    round_with_transcript(repo, out, builder)
    write_json(out / "sealed" / "secrets.json", {"X": secret})

    with pytest.raises(EvalError, match="Segredo"):
        write_agent_metrics(out, measure_agent(out))

    assert not (out / "agent-metrics.json").exists()


def test_save_needs_to_know_the_case(tmp_path: Path) -> None:
    standard_round().save(tmp_path)

    with pytest.raises(EvalError, match="caso"):
        save_measurement(tmp_path, measure_agent(tmp_path), "v", DAY, root=tmp_path / "m")


def saved(root: Path, name: str, builder: Builder, score: float | None, runs: Any = None) -> Path:
    folder = root / name
    out = root / f"{name}-round"
    make_round_dir = out
    builder.save(make_round_dir)
    write_agent_metrics_plain(make_round_dir, folder)
    if score is not None:
        write_json(folder / "score.json", {"grade": score})
    for index, data in enumerate(runs or []):
        write_json(folder / f"metrics-r{index}.json", data)
    return folder


def write_agent_metrics_plain(out: Path, folder: Path) -> None:
    folder.mkdir(parents=True)
    metrics = measure_agent(out)
    (folder / "agent-metrics.json").write_text(
        json.dumps(metrics.model_dump(mode="json")), encoding="utf-8"
    )


def row(result: dict[str, Any], metric: str) -> dict[str, Any]:
    return next(r for r in result["rows"] if r["metric"] == metric)


def test_compare_reports_differences_for_totals_and_stages(tmp_path: Path) -> None:
    fast = Builder()
    fast.call("uv run hdast probe mini", wait=10)
    slow = Builder()
    slow.call("uv run hdast probe mini", wait=40)
    slow.call("uv run hdast probe mini", wait=40)
    a = saved(tmp_path, "a", fast, 7.0)
    b = saved(tmp_path, "b", slow, 8.5)

    result = compare_measurements(a, b)

    assert row(result, "probe (comandos)")["diff"] == 1
    assert row(result, "nota")["diff"] == pytest.approx(1.5)
    assert row(result, "alcance: segundos")["a"] == pytest.approx(10.0)
    assert row(result, "alcance: segundos")["b"] == pytest.approx(81.0)


def test_compare_shows_missing_data_as_nd_never_zero(tmp_path: Path) -> None:
    builder = Builder()
    builder.call("uv run hdast probe mini")
    a = saved(tmp_path, "a", builder, None)
    b = saved(tmp_path, "b", builder, 9.0)

    result = compare_measurements(a, b)
    table = render_comparison(result)

    assert row(result, "nota")["a"] is None
    assert row(result, "nota")["diff"] is None
    assert "nota | n/d | 9 | n/d" in table
    assert "etapa da CLI scan (s) | n/d | n/d | n/d" in table


def run_file(stages: dict[str, Any], rules: list[dict[str, Any]], gap_total: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "stages_seconds": stages,
        "rules": {"totals": rules},
        "traffic": {"gaps": {"count": 1, "total_seconds": gap_total, "longest_seconds": gap_total}},
    }


def rule(plugin_id: str, time_ms: Any, name: str = "Regra") -> dict[str, Any]:
    return {"plugin_id": plugin_id, "name": name, "time_ms": time_ms, "requests": 1, "alerts": 0}


def test_compare_shows_cli_stages_gaps_and_the_ten_rules_with_most_time_difference(
    tmp_path: Path,
) -> None:
    builder = Builder()
    builder.call("uv run hdast probe mini")
    rules_a = [rule("40018", 5000, "SQL Injection"), rule("10021", 1000)]
    rules_b = [rule("40018", 35000, "SQL Injection"), rule("7", 2000)]
    rules_b += [rule(str(100 + n), 10 + n) for n in range(12)]
    a = saved(
        tmp_path,
        "a",
        builder,
        1.0,
        [run_file({"probe": 3, "scan": 100, "report": 1}, rules_a, 5)],
    )
    b = saved(
        tmp_path,
        "b",
        builder,
        1.0,
        [run_file({"probe": 4, "scan": 160, "report": None}, rules_b, 45.5)],
    )

    result = compare_measurements(a, b)

    assert row(result, "etapa da CLI scan (s)")["diff"] == 60
    assert row(result, "etapa da CLI probe (s)")["diff"] == 1
    assert row(result, "etapa da CLI report (s)")["b"] is None
    assert row(result, "etapa da CLI preflight (s)")["a"] is None
    assert row(result, "lacunas do proxy: total (s)")["diff"] == pytest.approx(40.5)
    rules = [r for r in result["rows"] if r["metric"].startswith("regra ZAP")]
    assert len(rules) == 10
    assert rules[0]["metric"] == "regra ZAP 40018 SQL Injection (s)"
    assert rules[0]["diff"] == 30
    assert rules[1]["metric"] == "regra ZAP 7 Regra (s)"
    assert rules[1]["a"] is None


def test_compare_shows_nd_when_the_run_metrics_are_missing(tmp_path: Path) -> None:
    builder = Builder()
    builder.call("uv run hdast probe mini")
    a = saved(tmp_path, "a", builder, 1.0)
    b = saved(tmp_path, "b", builder, 1.0)

    table = render_comparison(compare_measurements(a, b))

    assert "etapa da CLI scan (s) | n/d | n/d | n/d" in table
    assert "lacunas do proxy: total (s) | n/d | n/d | n/d" in table
    assert "regra ZAP" not in table


@pytest.mark.parametrize(
    "content",
    [
        {"outro": "formato"},
        [1, 2],
        {"schema_version": 2, "stages_seconds": {"scan": 9}},
        {"schema_version": "1", "stages_seconds": {"scan": 9}},
    ],
)
def test_compare_ignores_a_run_metrics_file_it_does_not_understand(
    tmp_path: Path, content: Any
) -> None:
    builder = Builder()
    builder.call("uv run hdast probe mini")
    a = saved(tmp_path, "a", builder, 1.0, [content])
    b = saved(tmp_path, "b", builder, 1.0, [content])

    result = compare_measurements(a, b)

    assert row(result, "etapa da CLI scan (s)")["a"] is None
    assert row(result, "etapa da CLI scan (s)")["diff"] is None


def test_compare_ignores_a_malformed_run_metrics_file(tmp_path: Path) -> None:
    builder = Builder()
    builder.call("uv run hdast probe mini")
    a = saved(tmp_path, "a", builder, 1.0)
    write(a / "metrics-quebrado.json", "{nao json")

    result = compare_measurements(a, a)

    assert row(result, "etapa da CLI scan (s)")["a"] is None


def test_compare_tolerates_wrong_types_inside_a_valid_run_metrics_file(tmp_path: Path) -> None:
    builder = Builder()
    builder.call("uv run hdast probe mini")
    bad = {
        "schema_version": 1,
        "stages_seconds": {"scan": "muito", "probe": True, "authz": 7},
        "rules": {"totals": [rule("1", "x"), "lixo", {"name": "sem id"}, rule("2", 3000)]},
        "traffic": {"gaps": "nada"},
    }
    a = saved(tmp_path, "a", builder, 1.0, [bad])

    result = compare_measurements(a, a)

    assert row(result, "etapa da CLI scan (s)")["a"] is None
    assert row(result, "etapa da CLI probe (s)")["a"] is None
    assert row(result, "etapa da CLI authz (s)")["a"] == 7
    assert row(result, "lacunas do proxy: total (s)")["a"] is None
    assert [r["metric"] for r in result["rows"] if r["metric"].startswith("regra")] == [
        "regra ZAP 2 Regra (s)"
    ]


def test_compare_needs_two_saved_measurements(tmp_path: Path) -> None:
    (tmp_path / "vazia").mkdir()

    with pytest.raises(EvalError, match=r"agent-metrics\.json"):
        compare_measurements(tmp_path / "vazia", tmp_path / "vazia")


def test_cli_measure_save_and_compare_end_to_end(
    repo: Path, out: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    round_with_transcript(repo, out)
    root = tmp_path / "m"
    args = ["measure", "--out", str(out), "--save", "v1-0", "--measurements-dir", str(root)]

    code = main(args, today=lambda: DAY)

    assert code == 0
    assert (out / "agent-metrics.json").is_file()
    assert (root / "2026-11-14-mini-v1-0" / "agent-metrics.json").is_file()
    capsys.readouterr()
    folder = str(root / "2026-11-14-mini-v1-0")
    assert main(["compare", folder, folder, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["rows"][0]["diff"] == 0


def test_cli_measure_reports_a_missing_transcript_with_exit_code_two(
    out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out.mkdir()

    assert main(["measure", "--out", str(out)]) == 2
    assert "transcript" in capsys.readouterr().err


def test_cli_measure_save_twice_fails_with_exit_code_two(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    round_with_transcript(repo, out)
    args = ["measure", "--out", str(out), "--save", "x", "--measurements-dir", str(tmp_path / "m")]

    assert main(args, today=lambda: DAY) == 0
    assert main(args, today=lambda: DAY) == 2


def test_render_comparison_writes_large_numbers_without_exponent() -> None:
    row = {"metric": "m", "a": 3497100.0, "b": 12.5, "diff": None}

    assert "m | 3497100 | 12.5 | n/d" in render_comparison({"a": "A", "b": "B", "rows": [row]})
