"""Leitura do transcript: `stream-json`, arquivo `.output` de subagente e texto livre."""

import json
from pathlib import Path
from typing import Any

from evals.runner.transcript import parse_transcript
from tests.unit.evals.support import write


def _tool_use(uuid: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "assistant",
        "uuid": uuid,
        "isSidechain": True,
        "agentId": "a1b2c3",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": f"toolu_{uuid}", "name": name, "input": arguments}
            ],
        },
    }


def _tool_result(uuid: str, text: str) -> dict[str, Any]:
    return {
        "type": "user",
        "uuid": uuid,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "x", "content": text}],
        },
    }


def _subagent_output() -> str:
    """Arquivo `.output` de um subagente do Claude Code: conversa e telemetria misturadas."""
    prompt = {"type": "user", "uuid": "u0", "message": {"role": "user", "content": "Rode curl."}}
    telemetry_copy = {
        "type": "api-request-blob",
        "agentId": "a1b2c3",
        "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "curl http://x"}}
        ],
    }
    rows = [
        prompt,
        {"type": "api-request", "agentId": "a1b2c3", "params": {}},
        _tool_use("u1", "Bash", {"command": "uv run hdast --json probe mini"}),
        telemetry_copy,
        _tool_result("u2", "ok"),
        _tool_use("u1", "Bash", {"command": "uv run hdast --json probe mini"}),
        {"type": "attachment", "attachment": {"note": "texto com printenv"}},
        {"type": "assistant", "uuid": "u3", "message": {"role": "assistant", "content": []}},
    ]
    return "\n".join(json.dumps(row) for row in rows)


def test_subagent_output_counts_each_tool_call_once_and_ignores_telemetry() -> None:
    transcript = parse_transcript(_subagent_output())

    assert transcript.structured
    assert transcript.shell_commands() == ["uv run hdast --json probe mini"]


def test_subagent_output_keeps_tool_results_in_the_raw_text_for_the_secret_search() -> None:
    transcript = parse_transcript(
        "\n".join(
            [
                json.dumps(_tool_use("u1", "Bash", {"command": "uv run hdast stack status"})),
                json.dumps(_tool_result("u2", "valor-vazado-123")),
            ]
        )
    )

    assert "valor-vazado-123" in transcript.raw


def test_subagent_output_reports_a_direct_http_call_made_by_the_agent() -> None:
    rows = [_tool_use("u1", "Bash", {"command": "curl -s http://clinica-piloto:8080/api/saude"})]

    transcript = parse_transcript("\n".join(json.dumps(row) for row in rows))

    assert transcript.shell_commands() == ["curl -s http://clinica-piloto:8080/api/saude"]


def test_single_bare_tool_use_documents_still_parse() -> None:
    raw = json.dumps({"type": "tool_use", "name": "Read", "input": {"file_path": "C:/w/.env"}})

    transcript = parse_transcript(raw)

    assert transcript.read_targets() == ["C:/w/.env"]
    assert transcript.raw == raw


def test_plain_text_is_not_structured(tmp_path: Path) -> None:
    write(tmp_path / "t.txt", "rodei curl")

    transcript = parse_transcript((tmp_path / "t.txt").read_text(encoding="utf-8"))

    assert not transcript.structured
    assert transcript.shell_commands() == ["rodei curl"]
