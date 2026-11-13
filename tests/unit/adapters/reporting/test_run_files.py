"""Armazém de artefatos de `scan` e `report` em disco: leitura estrita e escrita atômica."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.redaction import EvidenceMessage
from harness_dast.domain.scan_result import ScanProgress
from tests.unit.domain.report_helpers import RUN_ID, entry, operation, probe_result, scan_result


@pytest.fixture
def store(tmp_path: Path) -> FileRunArtifacts:
    return FileRunArtifacts(tmp_path)


def run_dir(tmp_path: Path) -> Path:
    directory = tmp_path / RUN_ID
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_scan_result_round_trips_and_no_temporary_file_is_left(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    result = scan_result([entry("obter", "GET", "/u/{id}", 4)])

    store.write_scan(RUN_ID, result)

    assert store.read_scan(RUN_ID) == result
    assert sorted(p.name for p in run_dir(tmp_path).iterdir()) == ["scan.json"]


def test_progress_alerts_and_evidence_are_written_as_documented(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    store.write_progress(
        RUN_ID,
        ScanProgress(
            run_id=RUN_ID, phase="scanning", status="running", index=2, total=5, updated_at="t"
        ),
    )
    store.write_alerts(RUN_ID, [{"id": "1", "alert": "Acentuação ok"}])
    store.write_evidence(RUN_ID, [EvidenceMessage(message_id=3, request_header="GET / HTTP/1.1")])

    directory = run_dir(tmp_path)
    progress = json.loads((directory / "scan-progress.json").read_text(encoding="utf-8"))
    alerts = json.loads((directory / "alerts.raw.json").read_text(encoding="utf-8"))
    evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
    assert (progress["phase"], progress["index"], progress["total"]) == ("scanning", 2, 5)
    assert alerts == {
        "schema_version": 1,
        "run_id": RUN_ID,
        "alerts": [{"id": "1", "alert": "Acentuação ok"}],
    }
    assert evidence["messages"][0]["message_id"] == 3
    assert store.read_alerts(RUN_ID) == ({"id": "1", "alert": "Acentuação ok"},)
    assert store.read_evidence(RUN_ID)[0].message_id == 3


def test_probe_manifest_and_audit_written_by_the_probe_are_readable(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    directory = run_dir(tmp_path)
    probe = probe_result([operation("obter", "GET", "/u")])
    (directory / "probe.json").write_text(probe.model_dump_json(), encoding="utf-8")
    line = {
        "seq": 1,
        "phase": "result",
        "timestamp": "t",
        "method": "GET",
        "scheme": "http",
        "host": "alvo",
        "port": 80,
        "path": "/u",
        "operation_id": "obter",
        "route": "zap",
        "status": 200,
        "duration_ms": 1,
    }
    (directory / "audit.jsonl").write_text(json.dumps(line) + "\n\n", encoding="utf-8")

    assert store.read_probe(RUN_ID) == probe
    assert [e.operation_id for e in store.read_audit(RUN_ID)] == ["obter"]


@pytest.mark.parametrize(
    "reader",
    ["read_manifest", "read_probe", "read_audit", "read_scan", "read_alerts", "read_findings"],
)
def test_missing_files_are_config_errors_that_name_the_command_to_rerun(
    store: FileRunArtifacts, reader: str
) -> None:
    with pytest.raises(ConfigError) as info:
        getattr(store, reader)(RUN_ID)

    assert info.value.hint
    assert "Rode" in info.value.hint


def test_optional_files_are_empty_or_none_when_absent(store: FileRunArtifacts) -> None:
    assert store.read_evidence(RUN_ID) == ()
    assert store.read_triage(RUN_ID) is None


@pytest.mark.parametrize(
    ("name", "content", "reader"),
    [
        ("scan.json", "{nao e json", "read_scan"),
        ("scan.json", "[]", "read_scan"),
        ("scan.json", '{"run_id": 1}', "read_scan"),
        ("probe.json", "", "read_probe"),
        ("alerts.raw.json", '{"alerts": "x"}', "read_alerts"),
        ("alerts.raw.json", '{"alerts": [1]}', "read_alerts"),
        ("alerts.raw.json", "[]", "read_alerts"),
        ("evidence.json", '{"messages": 3}', "read_evidence"),
        ("evidence.json", '{"messages": [{"x": 1}]}', "read_evidence"),
        ("audit.jsonl", "isto nao e json\n", "read_audit"),
        ("triage.json", "{", "read_triage"),
        ("findings.json", "null", "read_findings"),
    ],
)
def test_corrupt_or_malformed_files_are_config_errors_without_echoing_content(
    tmp_path: Path, store: FileRunArtifacts, name: str, content: str, reader: str
) -> None:
    (run_dir(tmp_path) / name).write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError) as info:
        getattr(store, reader)(RUN_ID)

    assert "ilegível" in info.value.message
    assert content.strip() == "" or content.strip() not in info.value.message


def test_non_utf8_and_oversized_files_are_refused(
    tmp_path: Path, store: FileRunArtifacts, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = run_dir(tmp_path)
    (directory / "scan.json").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(ConfigError, match="ilegível"):
        store.read_scan(RUN_ID)

    (directory / "probe.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("harness_dast.adapters.reporting.run_files.MAX_FILE_BYTES", 1)
    with pytest.raises(ConfigError, match="ilegível"):
        store.read_probe(RUN_ID)


def test_run_id_is_validated_before_it_becomes_a_folder(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    with pytest.raises(ConfigError, match="inválido"):
        store.read_scan("../fora")
    with pytest.raises(ConfigError, match="inválido"):
        store.write_scan("../fora", scan_result([]))
    assert not (tmp_path.parent / "fora").exists()


def test_write_failure_is_a_config_error_with_a_hint(tmp_path: Path) -> None:
    blocked = tmp_path / "ocupado"
    blocked.write_text("arquivo no lugar da pasta", encoding="utf-8")
    store = FileRunArtifacts(blocked)

    with pytest.raises(ConfigError, match="Não foi possível gravar") as info:
        store.write_scan(RUN_ID, scan_result([]))

    assert "HDAST_RUNS_DIR" in (info.value.hint or "")
