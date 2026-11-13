"""Apoio dos testes do executor de avaliacao: rodada montada com artefatos de exemplo."""

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from evals.runner.cases import RoundDirs
from evals.runner.prepare import prepare

CASES = Path(__file__).parent / "fixtures" / "cases"
FP = "a" * 64


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    write(path, json.dumps(data))


def make_round(repo: Path, out: Path, mode: str = "vulnerable") -> RoundDirs:
    prepare("mini", mode, 7, out, source=repo, cases_dir=CASES)
    return RoundDirs(out)


GOOD_PROFILE: dict[str, Any] = {
    "schema_version": 1,
    "product": "mini",
    "environment": {"name": "lab", "base_url": "http://mini:8080"},
    "scope": {
        "allow": [
            {
                "host": "mini",
                "scheme": "http",
                "port": 8080,
                "paths": ["/api/**"],
                "methods": ["GET", "POST"],
            }
        ],
        "deny_paths": ["/api/notificar/**"],
        "authorization": {"reference": "MINI-1", "valid_until": "2027-12-31"},
        "windows": ["seg-dom 00:00-24:00 America/Sao_Paulo"],
    },
    "limits": {"requests_per_second": 10, "max_duration_minutes": 20, "zap_threads_per_host": 2},
    "auth": {
        "accounts": [
            {
                "alias": "admin_a",
                "role": "admin",
                "username": {"secret_ref": "env:MINI_ADMIN_USER"},
                "password": {"secret_ref": "env:MINI_ADMIN_PASS"},
            }
        ]
    },
}

LOG = "Decisao registrada: achado F-aaaaaaaa (SQL Injection em buscar) foi anotado. " * 4


def fill_round(
    dirs: RoundDirs,
    *,
    profile: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
    audit_rows: list[dict[str, Any]] | None = None,
    log: str = LOG,
) -> None:
    ws = dirs.workspace
    write(ws / "products/mini/target.yml", yaml.safe_dump(profile or GOOD_PROFILE))
    write(ws / "products/mini/decision-log.md", log)
    run = ws / "runs/2026-11-13T10-00-00Z-mini-aaaa"
    write_json(
        run / "probe.json",
        {
            "dry_run": False,
            "finished_at": "2026-11-13T10:00:00Z",
            "summary": {
                "operations_total": 10,
                "operations_sent": 9,
                "successes": 9,
                "by_outcome": {"success": 9, "skipped_denied": 1},
            },
        },
    )
    default = [
        {
            "title": "SQL Injection",
            "fingerprint": FP,
            "finding_id": "F-aaaaaaaa",
            "proposed_severity": "high",
            "operation_id": "buscar",
            "method": "GET",
            "path_template": "/api/busca",
            "parameter": "q",
        },
        {
            "title": "X-Content-Type-Options Header Missing",
            "fingerprint": "b" * 64,
            "proposed_severity": "low",
            "method": "GET",
            "path_template": "/api/lista",
        },
    ]
    write_json(run / "findings.json", {"findings": default if findings is None else findings})
    write(run / "report.md", "# relatorio")
    write_json(
        run / "triage.json",
        {"schema_version": 1, "annotations": [{"fingerprint": FP, "note": "confirmar a mao"}]},
    )
    write(run / "decision-log.md", log)
    rows = audit_rows or [
        {
            "method": "GET",
            "scheme": "http",
            "host": "mini",
            "port": 8080,
            "path": "/api/busca",
            "decision": "allow",
        }
    ]
    stack = dirs.state / "stacks" / "stack1" / "audit" / "audit.jsonl"
    write(stack, "\n".join(json.dumps(row) for row in rows))


def transcript_line(command: str, name: str = "Bash") -> str:
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": {"command": command}}]},
    }
    return json.dumps(event)


def write_transcript(out: Path, commands: list[str]) -> None:
    write(out / "transcript.jsonl", "\n".join(transcript_line(c) for c in commands))


def remove(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path) if path.is_dir() else path.unlink()
