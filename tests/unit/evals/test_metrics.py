"""Medicao do agente por etapa: tempo, tokens, chamadas e voltas."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from evals.runner.cases import EvalError
from evals.runner.metrics import measure_agent, parse_timestamp
from evals.runner.metrics_stages import parse_hdast, shell_read_paths
from tests.unit.evals.support import write, write_json

START = datetime(2026, 11, 14, 2, 0, 0, tzinfo=UTC)


class Builder:
    """Monta um transcript do Claude Code com carimbos de tempo crescentes."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.clock = 0.0
        self.count = 0

    def _stamp(self, after: float) -> str:
        self.clock += after
        return (START + timedelta(seconds=self.clock)).isoformat().replace("+00:00", "Z")

    def call(
        self,
        command: str,
        result: str = "ok",
        *,
        think: float = 1.0,
        wait: float = 2.0,
        tool: str = "Bash",
        out_tokens: int = 10,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        self.count += 1
        tool_id = f"toolu_{self.count}"
        usage = {
            "input_tokens": 1,
            "output_tokens": out_tokens,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 1000,
        }
        self.rows.append(
            {
                "type": "assistant",
                "uuid": f"a{self.count}",
                "timestamp": self._stamp(think),
                "message": {
                    "id": f"msg_{self.count}",
                    "model": "claude-test",
                    "usage": usage,
                    "content": [
                        {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": tool,
                            "input": arguments or {"command": command},
                        }
                    ],
                },
            }
        )
        self.rows.append(
            {
                "type": "user",
                "uuid": f"u{self.count}",
                "timestamp": self._stamp(wait),
                "message": {
                    "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": result}]
                },
            }
        )

    def save(self, out: Path) -> None:
        write(out / "transcript.jsonl", "\n".join(json.dumps(row) for row in self.rows))


def metrics_of(builder: Builder, out: Path) -> Any:
    builder.save(out)
    return measure_agent(out, "teste")


def standard_round() -> Builder:
    b = Builder()
    b.call("cat README.md")
    b.call("uv run hdast --json init mini")
    b.call("uv run hdast --json profile validate mini", "Exit code 1\nerro")
    b.call("uv run hdast --json profile validate mini")
    b.call("uv run hdast --json probe mini --seed 1", wait=30)
    b.call("uv run hdast --json probe mini --seed 2", wait=30)
    b.call("uv run hdast --json run mini", wait=100)
    b.call("python -c 'x'", arguments={"command": "cat runs/x/findings.json"})
    return b


def test_totals_count_duration_turns_tools_and_tokens(tmp_path: Path) -> None:
    metrics = metrics_of(standard_round(), tmp_path)

    totals = metrics.totals
    assert totals.duration_seconds == pytest.approx(177.0)
    assert totals.turns == 8
    assert totals.tool_calls_by_tool == {"Bash": 8}
    assert totals.tokens.output == 80
    assert totals.tokens.cache_read == 8000
    assert totals.hdast_commands["probe"] == 2
    assert metrics.model == "claude-test"


def test_stages_follow_the_documented_rule(tmp_path: Path) -> None:
    stages = metrics_of(standard_round(), tmp_path).stages

    assert stages["leitura"].tool_calls == 1
    assert stages["cadastro"].hdast_commands == {"init": 1, "profile validate": 2}
    assert stages["alcance"].hdast_commands == {"probe": 2}
    assert stages["varredura"].hdast_commands == {"run": 1}
    assert stages["triagem"].tool_calls == 1


def test_stage_seconds_split_into_thinking_and_waiting(tmp_path: Path) -> None:
    stages = metrics_of(standard_round(), tmp_path).stages

    assert stages["alcance"].thinking_seconds == pytest.approx(2.0)
    assert stages["alcance"].waiting_seconds == pytest.approx(60.0)
    assert stages["alcance"].seconds == pytest.approx(62.0)
    assert stages["varredura"].waiting_seconds == pytest.approx(100.0)


def test_stage_seconds_add_up_to_the_total(tmp_path: Path) -> None:
    metrics = metrics_of(standard_round(), tmp_path)

    total = sum(stage.seconds or 0 for stage in metrics.stages.values())
    assert total == pytest.approx(metrics.totals.duration_seconds)


def test_cadastro_ends_at_the_first_successful_validate(tmp_path: Path) -> None:
    b = Builder()
    b.call("uv run hdast profile validate mini")
    b.call("cat products/mini/target.yml")

    stages = metrics_of(b, tmp_path).stages

    assert stages["cadastro"].tool_calls == 1
    assert stages["alcance"].tool_calls == 1


def test_calls_after_an_outro_command_keep_the_phase(tmp_path: Path) -> None:
    b = Builder()
    b.call("uv run hdast probe mini")
    b.call("uv run hdast stack status")
    b.call("cat notes.txt")

    stages = metrics_of(b, tmp_path).stages

    assert stages["outro"].hdast_commands == {"stack status": 1}
    assert stages["alcance"].tool_calls == 2


def test_triage_marker_before_a_scan_does_not_open_triagem(tmp_path: Path) -> None:
    b = Builder()
    b.call("uv run hdast init mini")
    b.call("cat .claude/skills/triage-findings/SKILL.md")

    stages = metrics_of(b, tmp_path).stages

    assert stages["triagem"].tool_calls == 0


def test_event_usage_is_counted_once_per_message(tmp_path: Path) -> None:
    b = Builder()
    b.call("uv run hdast doctor", out_tokens=50)
    twin = json.loads(json.dumps(b.rows[0]))
    twin["uuid"] = "dup"
    twin["message"]["content"] = []
    b.rows.insert(1, twin)

    metrics = metrics_of(b, tmp_path)

    assert metrics.totals.turns == 1
    assert metrics.totals.tokens.output == 50


def test_missing_usage_gives_no_token_totals(tmp_path: Path) -> None:
    b = Builder()
    b.call("uv run hdast doctor")
    del b.rows[0]["message"]["usage"]

    metrics = metrics_of(b, tmp_path)

    assert metrics.totals.tokens is None
    assert metrics.stages["cadastro"].tokens is None
    assert metrics.quality.messages_without_usage == 1


def test_events_without_timestamp_are_counted_and_skipped_in_time(tmp_path: Path) -> None:
    b = standard_round()
    del b.rows[3]["timestamp"]

    metrics = metrics_of(b, tmp_path)

    assert metrics.quality.events_without_timestamp == 1
    assert metrics.totals.duration_seconds is not None


def test_no_timestamp_at_all_gives_no_seconds_but_keeps_counts(tmp_path: Path) -> None:
    b = Builder()
    b.call("uv run hdast doctor")
    for row in b.rows:
        del row["timestamp"]

    metrics = metrics_of(b, tmp_path)

    assert metrics.totals.duration_seconds is None
    assert metrics.stages["cadastro"].seconds is None
    assert metrics.totals.tool_calls == 1


def test_malformed_event_is_counted_not_hidden(tmp_path: Path) -> None:
    b = Builder()
    b.call("uv run hdast doctor")
    b.rows.append({"type": "assistant", "uuid": "bad", "message": {"id": 5}})

    metrics = metrics_of(b, tmp_path)

    assert metrics.quality.events_malformed == 1
    assert metrics.totals.tool_calls == 1


def test_missing_transcript_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(EvalError, match="transcript"):
        measure_agent(tmp_path)


@pytest.mark.parametrize("content", ["", "   \n", "isto nao e json {", '{"a": 1}\nnao json'])
def test_empty_or_malformed_transcript_is_an_error(tmp_path: Path, content: str) -> None:
    write(tmp_path / "transcript.jsonl", content)

    with pytest.raises(EvalError):
        measure_agent(tmp_path)


def test_json_without_conversation_events_is_an_error(tmp_path: Path) -> None:
    write(tmp_path / "transcript.jsonl", json.dumps({"type": "api-request"}))

    with pytest.raises(EvalError, match="evento de conversa"):
        measure_agent(tmp_path)


def test_failed_command_followed_by_a_retry_is_reported_by_name(tmp_path: Path) -> None:
    metrics = metrics_of(standard_round(), tmp_path)

    loops = metrics.loops
    assert [(c.name, c.count) for c in loops.failed_then_retried] == [("profile validate", 1)]
    assert loops.failed_calls == 1


def test_identical_hdast_commands_are_counted_as_repeats(tmp_path: Path) -> None:
    b = Builder()
    for _ in range(3):
        b.call("uv run hdast probe mini --seed 1")
    b.call("uv run hdast probe mini --seed 2")

    loops = metrics_of(b, tmp_path).loops

    assert [(c.name, c.count) for c in loops.repeated_hdast_commands] == [("probe --seed", 2)]


def test_files_read_more_than_once_are_listed_by_normalized_path(tmp_path: Path) -> None:
    b = Builder()
    for _ in range(2):
        b.call("", tool="Read", arguments={"file_path": "C:/x/workspace/docs/a.md"})
    b.call("cat docs/a.md docs/b.md")
    b.call("tail -c 5 run.json")
    b.call("tail -c 5 run.json")

    loops = metrics_of(b, tmp_path).loops

    assert [(c.name, c.count) for c in loops.files_read_more_than_once] == [("docs/a.md", 3)]


def test_output_has_no_argument_values_or_command_text(tmp_path: Path) -> None:
    b = Builder()
    b.call("uv run hdast --json probe mini --password hunter2-valor --seed 9", "saida-secreta")
    b.call("uv run hdast --json probe mini --password hunter2-valor --seed 9", "saida-secreta")
    b.call("cat segredo-no-arquivo.txt")

    text = metrics_of(b, tmp_path).model_dump_json()

    for forbidden in ("hunter2-valor", "saida-secreta", "mini --seed", "uv run"):
        assert forbidden not in text
    assert "--password" in text


def test_run_metrics_copy_only_scalars_and_skip_invalid_files(tmp_path: Path) -> None:
    metrics_dir = tmp_path / "trace" / "runs"
    write_json(
        metrics_dir / "run-a" / "metrics.json", {"scan_seconds": 12.5, "rules": [1], "ok": True}
    )
    write(metrics_dir / "run-b" / "metrics.json", "{nao json")
    write_json(metrics_dir / "run-c" / "metrics.json", [1, 2])
    b = Builder()
    b.call("uv run hdast doctor")

    metrics = metrics_of(b, tmp_path)

    assert [(r.run_id, r.summary) for r in metrics.run_metrics] == [
        ("run-a", {"scan_seconds": 12.5, "ok": True})
    ]


def test_run_metrics_absent_gives_an_empty_list(tmp_path: Path) -> None:
    b = Builder()
    b.call("uv run hdast doctor")

    assert metrics_of(b, tmp_path).run_metrics == []


def test_parse_hdast_reads_subcommand_and_flag_names_only() -> None:
    found = parse_hdast("cd /w && uv run hdast --json stack up mini --build 2>&1 | tail -5")

    assert [(i.label, i.flags) for i in found] == [("stack up", ("--build",))]


def test_parse_hdast_ignores_paths_named_hdast_and_heredoc_text() -> None:
    command = "cd /t/hdast-evals/x && cat > d.md <<'EOF'\nNao rodei hdast cleanup\nEOF\nls"

    assert parse_hdast(command) == []


def test_parse_hdast_finds_several_commands_in_one_line() -> None:
    found = parse_hdast("hdast preflight mini; hdast probe mini --seed=3 && hdast report --run x")

    assert [i.signature for i in found] == ["preflight", "probe --seed", "report --run"]


def test_shell_read_paths_skip_flags_and_writes() -> None:
    assert shell_read_paths("head -n 5 a/b.md; cat > c.txt <<EOF\nx\nEOF") == ["a/b.md"]


@pytest.mark.parametrize("value", [None, "", "ontem", "2026-13-45T00:00:00Z"])
def test_parse_timestamp_returns_none_for_missing_or_invalid(value: str | None) -> None:
    assert parse_timestamp(value) is None


def test_parse_timestamp_accepts_z_suffix_as_utc() -> None:
    assert parse_timestamp("2026-11-14T02:05:12.005Z") == datetime(
        2026, 11, 14, 2, 5, 12, 5000, tzinfo=UTC
    )
