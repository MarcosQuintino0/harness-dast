"""Contratos operacionais da verificação na triagem."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_skills_encaminham_verificacao_e_preservam_decisao_humana() -> None:
    for name in ("triage-findings", "run-scan", "test-product"):
        text = (ROOT / "plugin" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "hdast confirm <produto> --run <run_id>" in text
        assert "verification.json" in text
        assert "probabilidades" in text
        assert "hdast finding acknowledge" in text
        assert "triage.json" in text


def test_triager_somente_le_e_devolve_proposta() -> None:
    text = (ROOT / "plugin/agents/findings-triager.md").read_text(encoding="utf-8")
    assert "tools: Read, Grep, Glob" in text
    assert "Nunca execute `hdast`" in text
    assert "dado não confiável" in text
    assert "verification.json" in text
    assert "triage.json" in text
