"""Prova candidata V1.11 nos três cenários do laboratório, operada pelo coordenador."""

import hashlib
import html
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from harness_dast.domain import html_safe
from harness_dast.domain.markdown_safe import escape_inline
from harness_dast.domain.redaction import redact_body, redact_header_block
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.verification import VerificationFile
from tests.integration.finding_confirmation_support import (
    confirm_individually,
    confirm_legacy,
    verification_summary,
)
from tests.integration.finding_verification_support import (
    ARTIFACTS,
    LabRun,
    VerificationArticleParser,
    check_ownership,
    findings,
    load_json,
    make_cli,
    prepare_root,
    run_id_for,
)
from tests.integration.lab_support import REPO

pytestmark = pytest.mark.integration

LEVEL_LABELS = {
    "reproduced": "Reproduzido",
    "likely": "Provável",
    "inconclusive": "Inconclusivo",
    "likely_false_positive": "Provável falso positivo",
    "not_verifiable": "Não verificável",
}


def _validate_presentations(
    lab: LabRun, folder: Path, verification: VerificationFile, report: FindingsReport
) -> None:
    """Confere um resultado real na seção de verificação dos três documentos."""
    if not verification.entries:
        for path in (folder / "panel" / "findings.html", folder / "report.html"):
            parser = VerificationArticleParser("")
            parser.feed(path.read_text(encoding="utf-8"))
            parser.close()
            assert parser.main_seen
            assert not parser.in_main
            assert "".join(parser.main_text).strip()
        assert (folder / "report.md").read_text(encoding="utf-8").strip()
        lab.summary["presentation_check"] = {"status": "not_exercised", "reason": "sem amostra"}
        lab.save()
        return
    lab.summary["presentation_check"] = {"status": "incomplete"}
    lab.save()
    assert (folder / "verification.json").is_file()
    entry = verification.entries[0]
    item = findings(report)[entry.fingerprint]
    finding_id = item["finding_id"]
    assert isinstance(finding_id, str)
    assert finding_id
    headers, _ = redact_header_block("Evidência\n" + entry.reason, lambda text: text)
    reason, _ = redact_body(headers.partition("\n")[2], lambda text: text, cap=400)
    label = LEVEL_LABELS[entry.level]
    paragraph = f"Verificação: {label} — {html.unescape(html_safe.text(reason))}"
    for path in (folder / "panel" / "findings.html", folder / "report.html"):
        parser = VerificationArticleParser(finding_id)
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        assert paragraph in parser.paragraphs, f"Verificação ausente ou incorreta em {path.name}."
    markdown = (folder / "report.md").read_text(encoding="utf-8")
    section = markdown.split("## Verificação dos achados", 1)
    assert len(section) == 2
    article = section[1].split(f"### {escape_inline(finding_id)} —", 1)
    assert len(article) == 2
    article_text = article[1].split("\n### ", 1)[0]
    assert f"**Verificação:** {label} — {escape_inline(reason)}" in article_text
    lab.summary["presentation_check"] = {
        "status": "validated",
        "fingerprint": entry.fingerprint,
        "finding_id": finding_id,
    }
    lab.save()


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
    _validate_presentations(lab, folder, verification, after_report)
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
    git = shutil.which("git")
    assert git is not None, "A prova exige Git para registrar a procedência."
    source = subprocess.run(  # noqa: S603 - Git local e referência fixa da própria worktree
        [git, "-C", str(REPO), "rev-parse", "HEAD", "HEAD^{tree}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.splitlines()
    assert len(source) == 2
    lab = LabRun(
        cli,
        token,
        metrics,
        case,
        {
            "phase": "candidate",
            "source_commit": source[0],
            "source_tree": source[1],
            "product": product,
            "mode": mode,
            "root": str(root),
            "profile_sha256": profile_hash,
            "commands": [],
            "outcome": "incomplete",
            "legacy": {
                "status": "pending" if os.environ.get("V111_LEGACY_MANIFEST") else "not_requested"
            },
        },
    )
    attempted_up = False
    try:
        assert lab.command("profile", "validate", product)[0] == 0
        attempted_up = True
        assert (
            lab.command("stack", "up", product, f"--{mode}", "--timeout", "600", timeout=850)[0]
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
