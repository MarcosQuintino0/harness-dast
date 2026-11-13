# ruff: noqa: S106
"""Arquivos de limpeza da execução: manifesto, registro, trilha e token de uso único."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from harness_dast.adapters.cleanup.run_files import (
    AUDIT_FILE,
    CONFIRMATION_FILE,
    CONFIRMATION_USED_FILE,
    MANIFEST_FILE,
    RECORD_FILE,
    FileCleanupRuns,
)
from harness_dast.domain.cleanup_confirmation import issue_record
from harness_dast.domain.cleanup_plan import CleanupAuditLine, CleanupRecord
from harness_dast.domain.errors import ConfigError
from tests.fakes.cleanup_ports import finished_manifest

RUN_ID = "2026-11-10T10-00-00Z-demo-7f3a"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def make(tmp_path: Path) -> tuple[FileCleanupRuns, Path]:
    directory = tmp_path / RUN_ID
    directory.mkdir()
    return FileCleanupRuns(tmp_path), directory


def record() -> CleanupRecord:
    return CleanupRecord(
        run_id=RUN_ID,
        product="demo",
        status="dry_run",
        script_sha256="h",
        statement_count=1,
        tables=("PEDIDO",),
        statements=(),
        total_rows=0,
        max_rows=10,
        confirmation_method="none",
        committed=False,
        rolled_back=True,
        started_at="2026-11-10T12:00:00+00:00",
        finished_at="2026-11-10T12:00:01+00:00",
        duration_ms=1000,
    )


def test_reads_the_manifest_written_by_the_probe(tmp_path: Path) -> None:
    runs, directory = make(tmp_path)
    manifest = finished_manifest(RUN_ID, "demo", NOW, finished_at=NOW)
    (directory / MANIFEST_FILE).write_text(manifest.model_dump_json(), encoding="utf-8")

    assert runs.read_manifest(RUN_ID) == manifest


def test_missing_run_or_manifest_reads_as_none_and_creates_nothing(tmp_path: Path) -> None:
    runs = FileCleanupRuns(tmp_path)

    assert runs.read_manifest(RUN_ID) is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("content", [b"{", b"[]", b'{"run_id": "x"}', b"x" * 300_000])
def test_malformed_or_oversized_manifest_is_a_config_error(tmp_path: Path, content: bytes) -> None:
    runs, directory = make(tmp_path)
    (directory / MANIFEST_FILE).write_bytes(content)

    with pytest.raises(ConfigError, match="manifesto"):
        runs.read_manifest(RUN_ID)


@pytest.mark.parametrize("run_id", ["../x", "a/b", "", "2026-13-99T00-00-00Z-demo-7f3a", "..\\x"])
def test_run_id_that_is_not_a_run_id_never_becomes_a_path(tmp_path: Path, run_id: str) -> None:
    runs = FileCleanupRuns(tmp_path)

    with pytest.raises(ConfigError, match="inválido"):
        runs.read_manifest(run_id)
    with pytest.raises(ConfigError, match="inválido"):
        runs.write_record(run_id, record())


def test_writes_the_record_atomically_without_leaving_temporaries(tmp_path: Path) -> None:
    runs, directory = make(tmp_path)

    runs.write_record(RUN_ID, record())

    assert json.loads((directory / RECORD_FILE).read_text(encoding="utf-8"))["status"] == "dry_run"
    assert sorted(path.name for path in directory.iterdir()) == [RECORD_FILE]


def test_audit_is_append_only(tmp_path: Path) -> None:
    runs, directory = make(tmp_path)
    for event in ("started", "finished"):
        runs.append_audit(
            RUN_ID,
            CleanupAuditLine(
                event=event,
                at=NOW.isoformat(),
                product="demo",
                run_id=RUN_ID,
                script_sha256="h",
                mode="dry_run",
                confirmation_method="none",
            ),
        )

    lines = (directory / AUDIT_FILE).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["started", "finished"]


def test_write_failure_is_a_config_error(tmp_path: Path) -> None:
    runs = FileCleanupRuns(tmp_path)  # a pasta da execução não existe

    with pytest.raises(ConfigError, match="gravar"):
        runs.write_record(RUN_ID, record())
    with pytest.raises(ConfigError, match="gravar"):
        runs.append_audit(
            RUN_ID,
            CleanupAuditLine(
                event="started",
                at="x",
                product="demo",
                run_id=RUN_ID,
                script_sha256="h",
                mode="execute",
                confirmation_method="token",
            ),
        )


def test_confirmation_roundtrip_stores_only_the_digest(tmp_path: Path) -> None:
    runs, directory = make(tmp_path)
    confirmation = issue_record(
        token="hdc-segredo",
        product="demo",
        run_id=RUN_ID,
        script_sha256="h",
        rows_ceiling=3,
        now=NOW,
    )

    runs.save_confirmation(RUN_ID, confirmation)

    assert runs.load_confirmation(RUN_ID) == confirmation
    assert "hdc-segredo" not in (directory / CONFIRMATION_FILE).read_text(encoding="utf-8")


def test_consuming_the_confirmation_works_exactly_once(tmp_path: Path) -> None:
    runs, directory = make(tmp_path)
    runs.save_confirmation(
        RUN_ID,
        issue_record(
            token="t", product="demo", run_id=RUN_ID, script_sha256="h", rows_ceiling=3, now=NOW
        ),
    )

    assert runs.consume_confirmation(RUN_ID) is True
    assert runs.consume_confirmation(RUN_ID) is False
    assert runs.load_confirmation(RUN_ID) is None
    assert (directory / CONFIRMATION_USED_FILE).exists()


def test_new_dry_run_replaces_the_pending_confirmation(tmp_path: Path) -> None:
    runs, _ = make(tmp_path)
    for token in ("um", "dois"):
        runs.save_confirmation(
            RUN_ID,
            issue_record(
                token=token,
                product="demo",
                run_id=RUN_ID,
                script_sha256="h",
                rows_ceiling=3,
                now=NOW,
            ),
        )

    loaded = runs.load_confirmation(RUN_ID)

    assert loaded is not None
    assert loaded == issue_record(
        token="dois", product="demo", run_id=RUN_ID, script_sha256="h", rows_ceiling=3, now=NOW
    )


@pytest.mark.parametrize("content", [b"", b"nao-json", b'{"token_sha256": 1}'])
def test_unreadable_confirmation_counts_as_no_token(tmp_path: Path, content: bytes) -> None:
    runs, directory = make(tmp_path)
    (directory / CONFIRMATION_FILE).write_bytes(content)

    assert runs.load_confirmation(RUN_ID) is None
