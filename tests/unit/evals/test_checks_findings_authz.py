"""Gabarito: os achados do estágio `authz` contam para H5, H6 e H7 (ADR 0027)."""

import json
from pathlib import Path

import yaml

from evals.runner.checks_findings import ACHADA, NAO_ACHADA, flaw_status, matches, read_findings
from evals.runner.models import Case, Matcher

ROOT = Path(__file__).resolve().parents[3]


def pilot_case() -> Case:
    data = yaml.safe_load((ROOT / "evals/cases/clinica-piloto/case.yml").read_text("utf-8"))
    return Case.model_validate(data)


def authz_finding(technique: str, path: str, fingerprint: str) -> dict[str, str]:
    return {
        "technique": technique,
        "path_template": path,
        "method": "GET",
        "proposed_severity": "high",
        "fingerprint": fingerprint,
        "title": "qualquer",
    }


def test_the_matcher_can_require_a_technique() -> None:
    finding = authz_finding("authz_horizontal", "/api/consultas/{}", "a")

    assert matches(finding, Matcher(technique="authz_horizontal", path_contains="/api/consultas"))
    assert not matches(finding, Matcher(technique="authz_vertical"))
    assert not matches(finding, Matcher(technique="zap_active_scan"))


def test_the_authz_findings_in_findings_json_are_read_next_to_the_zap_ones(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    zap = {"title": "SQL Injection", "fingerprint": "z", "technique": "zap_active_scan"}
    own = authz_finding("authz_horizontal", "/api/consultas/{}", "a")
    (run / "findings.json").write_text(
        json.dumps({"findings": [zap], "authz": {"findings": [own]}}), encoding="utf-8"
    )

    found = read_findings(tmp_path)

    assert {item["fingerprint"] for item in found} == {"z", "a"}


def test_a_findings_json_without_the_authz_section_still_reads(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    (run / "findings.json").write_text(
        json.dumps({"findings": [], "authz": None}), encoding="utf-8"
    )

    assert read_findings(tmp_path) == []


def test_h5_h6_and_h7_of_the_pilot_are_detectable_by_their_technique() -> None:
    flaws = {flaw.id: flaw for flaw in pilot_case().flaws}
    expected = {
        "H5": authz_finding("authz_horizontal", "/api/consultas/{}", "a"),
        "H6": authz_finding("authz_mass_assignment", "/api/me", "b"),
        "H7": authz_finding("authz_excessive_data", "/api/pacientes", "c"),
    }

    for flaw_id, finding in expected.items():
        assert flaws[flaw_id].detectable
        assert flaw_status(flaws[flaw_id], [finding]) == ACHADA
        assert flaw_status(flaws[flaw_id], []) == NAO_ACHADA


def test_a_zap_alert_on_the_same_path_does_not_count_for_the_authz_flaws() -> None:
    flaws = {flaw.id: flaw for flaw in pilot_case().flaws}
    zap = {
        "title": "X",
        "path_template": "/api/consultas/{}",
        "method": "GET",
        "technique": "zap_active_scan",
        "fingerprint": "z",
    }

    assert flaw_status(flaws["H5"], [zap]) == NAO_ACHADA
