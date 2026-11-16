"""Armazém de artefatos de `scan` e `report` em disco: leitura estrita e escrita atômica."""

import json
import os
from pathlib import Path

import pytest

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_result import ArtifactHashes, RunManifest
from harness_dast.domain.redaction import EvidenceMessage
from harness_dast.domain.rule_stats import OperationRules, RuleStat, RuleStatsFile
from harness_dast.domain.run import RunLimits
from harness_dast.domain.run_metrics import build_run_metrics
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


def test_missing_scan_json_says_the_report_needs_it_and_how_to_get_it(
    store: FileRunArtifacts,
) -> None:
    with pytest.raises(ConfigError) as info:
        store.read_scan(RUN_ID)

    hint = info.value.hint or ""
    assert "O report precisa do scan.json" in hint
    assert "--skip-scan" in hint
    assert "hdast scan PRODUTO --run RUN_ID" in hint


def test_optional_files_are_empty_or_none_when_absent(store: FileRunArtifacts) -> None:
    assert store.read_evidence(RUN_ID) == ()
    assert store.read_triage(RUN_ID) is None


def test_triage_with_utf8_bom_is_read_when_an_editor_wrote_the_mark(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    triage = {"schema_version": 1, "annotations": []}
    (run_dir(tmp_path) / "triage.json").write_bytes(
        b"\xef\xbb\xbf" + json.dumps(triage).encode("utf-8")
    )
    assert store.read_triage(RUN_ID) == triage


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


def test_write_survives_a_reader_holding_the_file_for_a_moment(
    tmp_path: Path, store: FileRunArtifacts, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace = os.replace
    refusals = {"left": 2}

    def flaky_replace(source: Path, target: Path) -> None:
        if refusals["left"] > 0:
            refusals["left"] -= 1
            raise PermissionError("arquivo em uso por outro processo")
        real_replace(source, target)

    monkeypatch.setattr("harness_dast.adapters.reporting.run_files.os.replace", flaky_replace)
    monkeypatch.setattr("harness_dast.adapters.reporting.run_files.time.sleep", lambda _s: None)

    store.write_progress(
        RUN_ID,
        ScanProgress(
            run_id=RUN_ID, phase="scanning", status="running", index=1, total=2, updated_at="t"
        ),
    )

    assert (run_dir(tmp_path) / "scan-progress.json").is_file()
    assert refusals["left"] == 0


def test_write_gives_up_with_a_config_error_when_the_file_stays_locked(
    store: FileRunArtifacts, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_locked(source: Path, target: Path) -> None:
        raise PermissionError("arquivo em uso por outro processo")

    monkeypatch.setattr("harness_dast.adapters.reporting.run_files.os.replace", always_locked)
    monkeypatch.setattr("harness_dast.adapters.reporting.run_files.time.sleep", lambda _s: None)

    with pytest.raises(ConfigError):
        store.write_alerts(RUN_ID, [])


def test_missing_exchanges_json_is_a_config_error_that_names_the_probe(
    store: FileRunArtifacts,
) -> None:
    with pytest.raises(ConfigError) as info:
        store.read_exchanges(RUN_ID)

    assert "Rode o probe" in (info.value.hint or "")


def test_missing_authz_json_means_the_stage_did_not_run(store: FileRunArtifacts) -> None:
    assert store.read_authz(RUN_ID) is None


@pytest.mark.parametrize("name", ["exchanges.json", "authz.json"])
@pytest.mark.parametrize(
    "content",
    [
        "",
        "{nao e json",
        "[]",
        "null",
        '{"run_id": 1}',
        '{"schema_version": 1, "run_id": "r", "product": "p", "exchanges": "x"}',
        '{"schema_version": 1, "run_id": "r", "product": "p", "findings": [1]}',
    ],
)
def test_corrupt_or_malformed_exchanges_and_authz_are_config_errors_without_echoing_content(
    tmp_path: Path, store: FileRunArtifacts, name: str, content: str
) -> None:
    (run_dir(tmp_path) / name).write_text(content, encoding="utf-8")
    reader = store.read_exchanges if name == "exchanges.json" else store.read_authz

    with pytest.raises(ConfigError) as info:
        reader(RUN_ID)

    assert "ilegível" in info.value.message
    assert content.strip() == "" or content.strip() not in info.value.message


def test_exchanges_json_with_a_tampered_target_is_refused(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    record = {
        "operation_id": "o",
        "method": "GET",
        "path": "/p",
        "target": "//evil.test/x",
        "account": "a",
        "status": 200,
    }
    text = json.dumps({"run_id": RUN_ID, "product": "p", "exchanges": [record]})
    (run_dir(tmp_path) / "exchanges.json").write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError, match="ilegível"):
        store.read_exchanges(RUN_ID)


def test_non_utf8_exchanges_and_authz_are_refused(tmp_path: Path, store: FileRunArtifacts) -> None:
    directory = run_dir(tmp_path)
    (directory / "exchanges.json").write_bytes(b"\xff\xfe\x00bad")
    (directory / "authz.json").write_bytes(b"\xff\xfe\x00bad")

    with pytest.raises(ConfigError, match="ilegível"):
        store.read_exchanges(RUN_ID)
    with pytest.raises(ConfigError, match="ilegível"):
        store.read_authz(RUN_ID)


# ------------------------------------------------------------------ medição (ADR 0031)


def _rule_stats() -> RuleStatsFile:
    rule = RuleStat(plugin_id=6, name="Path Traversal", state="completed", time_ms=1175)
    return RuleStatsFile(
        run_id=RUN_ID,
        zap_version="2.17.0",
        operations=(OperationRules(operation_id="obter", scan_id="0", rules=(rule,)),),
    )


def test_rule_stats_round_trip_and_the_file_is_listed_as_a_known_artifact(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    store.write_rule_stats(RUN_ID, _rule_stats())

    assert store.read_rule_stats(RUN_ID) == _rule_stats()
    assert "rule-stats.json" in store.existing_files(RUN_ID)
    assert sorted(p.name for p in run_dir(tmp_path).iterdir()) == ["rule-stats.json"]


def test_missing_rule_stats_means_the_scan_did_not_write_them(store: FileRunArtifacts) -> None:
    run_dir(store._runs_dir)  # a pasta existe, o arquivo não

    assert store.read_rule_stats(RUN_ID) is None


@pytest.mark.parametrize(
    "content",
    [
        "{",
        "[]",
        '{"run_id": "x", "operations": "y"}',
        '{"run_id": "x", "operations": [{"operation_id": "a", "scan_id": "0", "rules": [{}]}]}',
    ],
)
def test_corrupt_or_malformed_rule_stats_are_config_errors(
    tmp_path: Path, store: FileRunArtifacts, content: str
) -> None:
    (run_dir(tmp_path) / "rule-stats.json").write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError, match=r"rule-stats.json"):
        store.read_rule_stats(RUN_ID)


def test_metrics_are_written_as_valid_json_and_listed_as_a_known_artifact(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    metrics = build_run_metrics(
        manifest=RunManifest(
            run_id=RUN_ID,
            command="probe",
            product="vampi",
            harness_version="1",
            hashes=ArtifactHashes(),
            limits=RunLimits(
                requests_per_second=5, max_duration_minutes=60, zap_threads_per_host=2
            ),
            seed=1,
            started_at="2026-11-13T05:15:30+00:00",
        ),
        probe=None,
        scan=None,
        authz=None,
        rule_stats=None,
        proxy_rows=None,
        stages=None,
        run_window=None,
        report_seconds=None,
        path_mode="strict",
        harness_version="1",
        generated_at="2026-11-13T05:30:00+00:00",
    )

    store.write_metrics(RUN_ID, metrics)

    written = json.loads((run_dir(tmp_path) / "metrics.json").read_text(encoding="utf-8"))
    assert written["schema_version"] == 1
    assert written["run_id"] == RUN_ID
    assert written["stages_seconds"]["scan"] is None
    assert "metrics.json" in store.existing_files(RUN_ID)
