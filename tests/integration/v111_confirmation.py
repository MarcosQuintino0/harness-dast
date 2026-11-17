"""Confirma??o individual e verifica??o de execu??es legadas do laborat?rio V1.11."""

from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.confirmation import select_confirmation_findings
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.run import is_run_id
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.verification import VerificationFile
from tests.integration.lab_support import read_jsonl
from tests.integration.v111_support import ARTIFACTS, LabRun, findings, load_json, report_items


def verification_summary(report: FindingsReport, verification: VerificationFile) -> dict[str, Any]:
    """Valida identidade, classificações e seleção de achados."""
    assert verification.product == report.product
    assert verification.run_id == report.run_id
    known = findings(report)
    assert len(verification.entries) == min(len(known), 30)
    assert {entry.fingerprint for entry in verification.entries} <= set(known)
    for entry in verification.entries:
        assert entry.reason.strip()
        if entry.recipe is None:
            assert entry.level in {"not_verifiable", "inconclusive"}
        if entry.level == "reproduced":
            assert entry.recipe is not None
    return {
        "count": len(verification.entries),
        "levels": dict(Counter(entry.level for entry in verification.entries)),
        "reasons": dict(Counter(entry.reason for entry in verification.entries)),
        "recipes": dict(Counter(entry.recipe or "none" for entry in verification.entries)),
    }


def confirm_individually(
    lab: LabRun, product: str, run_id: str, report: FindingsReport
) -> VerificationFile:
    """Executa cada fingerprint selecionado uma vez e mede o orçamento isoladamente."""
    folder = lab.cli.runs / run_id
    source = folder / "findings.json"
    original = source.read_bytes()
    selected = select_confirmation_findings(report_items(report), 30, None)
    records: list[dict[str, Any]] = []
    lab.summary["confirmations"] = records
    current = VerificationFile(schema_version=1, product=product, run_id=run_id, entries=())
    for item in selected:
        fingerprint = item.fingerprint
        audit = folder / "audit.jsonl"
        start = len(read_jsonl(audit))
        record: dict[str, Any] = {"fingerprint": fingerprint, "exit_code": None}
        records.append(record)
        lab.save()
        try:
            code, envelope = lab.command(
                "confirm", product, "--run", run_id, "--finding", fingerprint
            )
            record["exit_code"] = code
        finally:
            added = read_jsonl(audit)[start:]
            allowed = sum(
                row.get("phase") == "decision" and row.get("decision") == "allowed" for row in added
            )
            record["allowed"] = allowed
            lab.save()
            assert source.read_bytes() == original, "Achados foram alterados pela confirmação."
        data = envelope.get("data")
        if isinstance(data, dict):
            record["recipe_requests"] = data.get("recipe_requests")
            record["session_requests"] = data.get("session_requests")
        lab.save()
        assert code == 0, "Confirmação individual falhou; veja o resumo parcial."
        assert isinstance(data, dict)
        recipe, session = data.get("recipe_requests"), data.get("session_requests")
        assert type(recipe) is int
        assert type(session) is int
        assert recipe >= 0
        assert session >= 0
        assert recipe + session == allowed
        assert allowed <= 12
        updated = VerificationFile.model_validate(load_json(folder / "verification.json"))
        assert updated.product == product
        assert updated.run_id == run_id
        assert VerificationFile.model_validate(data["verification"]) == updated
        previous = {entry.fingerprint: entry for entry in current.entries}
        entries = {entry.fingerprint: entry for entry in updated.entries}
        assert set(entries) == set(previous) | {fingerprint}
        assert all(entries[key] == value for key, value in previous.items())
        entry = entries[fingerprint]
        assert entry.reason.strip()
        if entry.recipe is None:
            assert entry.level in {"inconclusive", "not_verifiable"}
        record.update(level=entry.level, reason=entry.reason, recipe=entry.recipe)
        current = updated
        lab.save()
    lab.summary["confirmation_totals"] = {
        key: sum(record[key] for record in records)
        for key in ("recipe_requests", "session_requests", "allowed")
    }
    return current


class LegacyRun(BaseModel):
    """Identidade fornecida pelo coordenador para uma execução de baseline."""

    model_config = ConfigDict(extra="forbid", strict=True)
    runs_dir: str
    run_id: str


def confirm_legacy(lab: LabRun, product: str, manifest_path: str) -> None:
    """Confirma uma baseline sem recibos, usando a pilha candidata e sem recriar relatórios."""
    legacy: dict[str, Any] = {"status": "incomplete", "manifest": manifest_path}
    lab.summary["legacy"] = legacy
    lab.save()
    try:
        _confirm_legacy(lab, product, manifest_path, legacy)
    except (AssertionError, KeyError, OSError, TypeError, ValueError) as error:
        legacy["status"] = "failed"
        legacy["error_type"] = type(error).__name__
        lab.save()
        raise


def _confirm_legacy(lab: LabRun, product: str, manifest_path: str, legacy: dict[str, Any]) -> None:
    legacy["stage"] = "manifest"
    path = Path(manifest_path)
    if not path.is_absolute() or not path.resolve().is_relative_to(ARTIFACTS.resolve()):
        raise ValueError("Manifesto legado deve estar nos artefatos da V1.11.")
    spec = LegacyRun.model_validate(load_json(path)[lab.case])
    directory = Path(spec.runs_dir)
    if not directory.is_absolute() or not directory.resolve().is_relative_to(ARTIFACTS.resolve()):
        raise ValueError("Runs legados devem estar nos artefatos da V1.11.")
    if not is_run_id(spec.run_id):
        raise ValueError("Identidade do run legado inválida.")
    directory = directory.resolve()
    folder = directory / spec.run_id
    legacy.update(
        run_id=spec.run_id,
        runs_dir=str(directory),
        verification_file=str(folder / "verification.json"),
        stage="identity",
    )
    lab.save()
    baseline = load_json(directory.parent / "summary.json")
    source_commit = baseline.get("source_commit")
    assert isinstance(source_commit, str)
    assert source_commit.startswith("44ef387")
    assert baseline.get("product") == product
    assert baseline.get("mode") == lab.summary["mode"]
    assert baseline.get("run_id") == spec.run_id
    run = RunSummary.model_validate(load_json(folder / "run.json"))
    assert run.product == product
    assert run.run_id == spec.run_id
    assert run.status in {"completed", "findings"}
    legacy["stage"] = "scan_without_binding"
    scan = load_json(folder / "scan.json")
    assert scan.get("product") == product
    assert scan.get("run_id") == spec.run_id
    assert scan.get("status") == "completed"
    entries = scan.get("entries")
    assert isinstance(entries, list)
    assert all(isinstance(entry, dict) and entry.get("seed_binding") is None for entry in entries)
    source = folder / "findings.json"
    original = source.read_bytes()
    report = FindingsReport.model_validate(load_json(source))
    assert report.product == product
    assert report.run_id == spec.run_id
    assert not (folder / "verification.json").exists(), "Verificação legada já existe."
    saved = lab.cli.env["HDAST_RUNS_DIR"]
    lab.cli.env["HDAST_RUNS_DIR"] = str(directory)
    audit = folder / "audit.jsonl"
    audit_start = len(read_jsonl(audit))
    try:
        legacy["stage"] = "confirm"
        code, envelope = lab.command("confirm", product, "--run", spec.run_id)
        legacy["exit_code"] = code
        added = read_jsonl(audit)[audit_start:]
        legacy["allowed"] = sum(
            row.get("phase") == "decision" and row.get("decision") == "allowed" for row in added
        )
        lab.save()
        assert code == 0, "Confirmação do legado falhou."
        data = envelope.get("data")
        assert isinstance(data, dict)
        legacy["recipe_requests"] = data.get("recipe_requests")
        legacy["session_requests"] = data.get("session_requests")
        lab.save()
        assert type(data.get("recipe_requests")) is int
        assert type(data.get("session_requests")) is int
        assert data["recipe_requests"] == 0
        assert data["session_requests"] == 0
        assert legacy["allowed"] == 0
        verification = VerificationFile.model_validate(data["verification"])
        assert verification.product == product
        assert verification.run_id == spec.run_id
        expected = select_confirmation_findings(report_items(report), 30, None)
        assert {entry.fingerprint for entry in verification.entries} == {
            item.fingerprint for item in expected
        }
        file = folder / "verification.json"
        if verification.entries:
            assert VerificationFile.model_validate(load_json(file)) == verification
        else:
            assert not file.exists()
            legacy["verification_file"] = None
        legacy["entries"] = [
            {
                "fingerprint": entry.fingerprint,
                "level": entry.level,
                "reason": entry.reason,
                "recipe": entry.recipe,
            }
            for entry in verification.entries
        ]
        assert all(entry.reason.strip() for entry in verification.entries)
        assert all(
            entry.level != "reproduced"
            for entry in verification.entries
            if entry.recipe in {"sql_boolean", "sql_time", "xss_reflected", "internal_error"}
        )
        legacy.update(status="completed", stage="completed")
    finally:
        lab.cli.env["HDAST_RUNS_DIR"] = saved
        legacy["findings_unchanged"] = source.read_bytes() == original
        lab.save()
        assert legacy["findings_unchanged"], "Achados legados foram alterados."
