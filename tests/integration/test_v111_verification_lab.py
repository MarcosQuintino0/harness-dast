"""Prova candidata V1.11 nos três cenários do laboratório, operada pelo coordenador."""

import hashlib
import os
from pathlib import Path

import pytest

from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.verification import VerificationFile
from tests.integration.v111_support import (
    ARTIFACTS,
    LabRun,
    check_ownership,
    confirm_individually,
    confirm_legacy,
    findings,
    load_json,
    make_cli,
    prepare_root,
    run_id_for,
    verification_summary,
)

pytestmark = pytest.mark.integration


def _settings() -> tuple[str, str, Path]:
    root = os.environ.get("V111_LAB_ROOT")
    token = os.environ.get("V111_LOCK_TOKEN")
    metrics = os.environ.get("HDAST_IT_METRICS_DIR")
    if not root or not token or not metrics:
        pytest.skip("Defina V111_LAB_ROOT, V111_LOCK_TOKEN e HDAST_IT_METRICS_DIR.")
    target = Path(metrics)
    if not target.is_absolute():
        pytest.fail("HDAST_IT_METRICS_DIR deve ser absoluto.")
    target = target.resolve()
    if target == ARTIFACTS.resolve() or not target.is_relative_to(ARTIFACTS.resolve()):
        pytest.fail("HDAST_IT_METRICS_DIR deve ficar abaixo de artefatos/v1-11.")
    check_ownership(token)
    return root, token, target


def _summarize_run(lab: LabRun, run_id: str, code: int) -> tuple[Path, bool]:
    folder = lab.cli.runs / run_id
    run = RunSummary.model_validate(load_json(folder / "run.json"))
    assert run.product == lab.summary["product"]
    assert run.run_id == run_id
    assert run.exit_code == code
    scan = load_json(folder / "scan.json") if (folder / "scan.json").is_file() else {}
    status = scan.get("status")
    stages = {stage.name: stage.status for stage in run.stages}
    partial = status != "completed" or stages.get("scan") != "ok"
    lab.summary.update(
        run_id=run_id,
        run_status=run.status,
        run_exit=code,
        stages=stages,
        scan_status=status,
        scan_partial=partial,
        scan_entries=len(scan.get("entries", [])),
    )
    lab.save()
    return folder, partial


def _report(lab: LabRun, product: str, run_id: str) -> int:
    code, _ = lab.command("report", product, "--run", run_id)
    return code


def _confirm_and_report(lab: LabRun, product: str, run_id: str, folder: Path) -> None:
    if not (folder / "findings.json").is_file():
        assert _report(lab, product, run_id) in {0, 1}
    before = FindingsReport.model_validate(load_json(folder / "findings.json"))
    assert before.product == product
    assert before.run_id == run_id
    before_findings = findings(before)
    verification = confirm_individually(lab, product, run_id, before)
    lab.summary["verification"] = verification_summary(before, verification)
    verification_path = folder / "verification.json"
    assert (
        findings(FindingsReport.model_validate(load_json(folder / "findings.json")))
        == before_findings
    )
    assert _report(lab, product, run_id) in {0, 1}
    after_report = FindingsReport.model_validate(load_json(folder / "findings.json"))
    assert findings(after_report) == before_findings
    if verification_path.is_file():
        assert VerificationFile.model_validate(load_json(verification_path)) == verification
    panel, _ = lab.command("panel", product, "--run", run_id)
    assert panel == 0
    pages = sorted(path.name for path in (folder / "panel").glob("*.html"))
    lab.summary["html_pages"] = pages
    lab.summary["html_page_count"] = len(pages)
    lab.summary["findings_count"] = len(before_findings)
    lab.summary["findings_by_severity"] = {
        severity: sum(value["proposed_severity"] == severity for value in before_findings.values())
        for severity in sorted({value["proposed_severity"] for value in before_findings.values()})
    }
    lab.summary["coverage_partial"] = before.coverage.partial
    assert "summary.html" in pages
    assert (folder / "report.html").is_file()
    lab.save()


@pytest.mark.parametrize(
    ("product", "mode"),
    [("clinica-piloto", "vulnerable"), ("clinica-piloto", "secure"), ("vampi", "vulnerable")],
)
def test_verificacao_aditiva_apos_varredura_completa(product: str, mode: str) -> None:
    """Usa perfis originais, sem seleção por gabarito e com pilha do wrapper exclusivo."""
    root_text, token, metrics = _settings()
    case = f"{product}-{mode}"
    assert not (metrics / f"{case}.json").exists(), "Métricas existentes devem ser preservadas."
    root = prepare_root(root_text, case)
    cli, profile_hash = make_cli(root, product)
    lab = LabRun(
        cli,
        token,
        metrics,
        case,
        {
            "product": product,
            "mode": mode,
            "root": str(root),
            "profile_sha256": profile_hash,
            "commands": [],
            "outcome": "incomplete",
        },
    )
    attempted_up = False
    try:
        assert lab.command("profile", "validate", product)[0] == 0
        attempted_up = True
        assert (
            lab.command(
                "stack", "up", product, f"--{mode}", "--build", "--timeout", "600", timeout=850
            )[0]
            == 0
        )
        code, envelope = lab.command("run", product)
        run_id = run_id_for(cli, envelope)
        lab.summary["run_id"] = run_id
        folder, partial = _summarize_run(lab, run_id, code)
        if (folder / "scan.json").is_file():
            _confirm_and_report(lab, product, run_id, folder)
        assert code in {0, 1}, "Run falhou; evidências parciais preservadas."
        assert not partial, "Scan parcial; evidências preservadas."
        assert (
            hashlib.sha256((cli.products / product / "target.yml").read_bytes()).hexdigest()
            == profile_hash
        )
        legacy_manifest = os.environ.get("V111_LEGACY_MANIFEST")
        if legacy_manifest:
            confirm_legacy(lab, product, legacy_manifest)
        lab.summary["outcome"] = "run_completed"
    finally:
        if "run_id" not in lab.summary:
            runs = list(cli.runs.glob("*/run.json"))
            if len(runs) == 1:
                lab.summary["run_id"] = runs[0].parent.name
                scan_file = runs[0].parent / "scan.json"
                scan = load_json(scan_file) if scan_file.is_file() else {}
                lab.summary["scan_status"] = scan.get("status")
                lab.summary["scan_partial"] = scan.get("status") != "completed"
        try:
            if attempted_up:
                down, _ = lab.command("stack", "down", timeout=300)
                lab.summary["stack_down_exit"] = down
                if down == 0 and lab.summary["outcome"] == "run_completed":
                    lab.summary["outcome"] = "completed"
        finally:
            lab.save()
        if attempted_up:
            assert lab.summary["stack_down_exit"] == 0, "Falha ao encerrar a própria pilha."
