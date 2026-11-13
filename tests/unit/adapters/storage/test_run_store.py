"""Armazém de execuções no sistema de arquivos."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from harness_dast.adapters.storage.run_store import FileRunStore
from harness_dast.domain.audit import decision_entry, result_entry
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.probe_result import (
    ArtifactHashes,
    ProbeResult,
    RunManifest,
    summarize_results,
)
from harness_dast.domain.run import RunLimits

RUN = "2026-11-10T12-00-00Z-agenda-7f3a"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def manifest(status: str = "running") -> RunManifest:
    return RunManifest(
        run_id=RUN,
        command="probe",
        product="agenda",
        harness_version="0",
        hashes=ArtifactHashes(target_yml="a" * 64),
        limits=RunLimits(requests_per_second=5, max_duration_minutes=60, zap_threads_per_host=2),
        seed=1,
        started_at=NOW.isoformat(),
        status=status,
    )


def request() -> HttpRequest:
    return HttpRequest(method="GET", url="https://h.example.net/api/x?a=1", operation_id="op")


def test_audit_lines_are_appended_in_order_as_json_lines(tmp_path: Path) -> None:
    store = FileRunStore(tmp_path / "runs")

    store.append_audit(RUN, decision_entry(1, NOW, request()))
    store.append_audit(RUN, result_entry(1, NOW, request(), status=200, error=None, duration_ms=5))

    lines = (tmp_path / "runs" / RUN / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [(p["seq"], p["phase"]) for p in parsed] == [(1, "decision"), (1, "result")]
    assert parsed[0]["query_names"] == ["a"]


def test_audit_is_append_only_across_store_instances(tmp_path: Path) -> None:
    FileRunStore(tmp_path).append_audit(RUN, decision_entry(1, NOW, request()))
    FileRunStore(tmp_path).append_audit(RUN, decision_entry(2, NOW, request()))

    assert len((tmp_path / RUN / "audit.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_manifest_is_replaced_atomically_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    store = FileRunStore(tmp_path)

    store.write_manifest(RUN, manifest("running"))
    store.write_manifest(RUN, manifest("completed"))

    folder = tmp_path / RUN
    assert (
        json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["status"] == "completed"
    )
    assert sorted(p.name for p in folder.iterdir()) == ["manifest.json"]


def test_probe_result_is_written_as_readable_json(tmp_path: Path) -> None:
    result = ProbeResult(
        run_id=RUN,
        product="agenda",
        dry_run=False,
        status="completed",
        seed=1,
        started_at="a",
        finished_at="b",
        summary=summarize_results([], 0),
        operations=(),
    )

    FileRunStore(tmp_path).write_probe(RUN, result)

    data = json.loads((tmp_path / RUN / "probe.json").read_text(encoding="utf-8"))
    assert data["run_id"] == RUN
    assert "notice" in data


@pytest.mark.parametrize("run_id", ["../fora", "a/b", "", "2026-11-10", RUN + "/..", "C:\\x"])
def test_a_run_id_that_could_escape_the_runs_dir_is_refused(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ConfigError):
        FileRunStore(tmp_path / "runs").write_manifest(run_id, manifest())

    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())


def test_write_failures_become_config_errors_with_a_hint(tmp_path: Path) -> None:
    blocker = tmp_path / "runs"
    blocker.write_text("sou um arquivo, não uma pasta", encoding="utf-8")

    actions: list[Callable[[FileRunStore], None]] = [
        lambda s: s.write_manifest(RUN, manifest()),
        lambda s: s.append_audit(RUN, decision_entry(1, NOW, request())),
    ]
    for action in actions:
        with pytest.raises(ConfigError) as info:
            action(FileRunStore(blocker))
        assert "HDAST_RUNS_DIR" in (info.value.hint or "")
