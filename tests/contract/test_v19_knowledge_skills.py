"""Contrato das orientações de conhecimento e ausência de pistas da avaliação."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ("onboard-product", "fix-reachability", "run-scan", "test-product")


def _section(name: str) -> str:
    text = (ROOT / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    return text.split("## Conhecimento em nova execução", 1)[1].split("\n## ", 1)[0].lower()


@pytest.mark.parametrize("name", SKILLS)
def test_conhecimento_preserva_autorizacao_e_nao_transporta_estado_efemero(name: str) -> None:
    section = _section(name)

    assert "observação não concede permissão" in section
    for term in ("tokens", "cookies", "credenciais", "respostas integrais", "gabarito"):
        assert term in section
    assert "identificadores de recursos" in section


@pytest.mark.parametrize("name", ["fix-reachability", "run-scan", "test-product"])
def test_resultado_desconhecido_de_mutacao_nao_e_repetido(name: str) -> None:
    section = _section(name)

    assert "resultado desconhecido" in section
    assert "não é sucesso" in section
    assert "às cegas" in section
    assert "verifique o estado" in section


def test_reuso_exige_prova_e_reavaliacao_de_dependencias() -> None:
    onboarding = _section("onboard-product")
    reachability = _section("fix-reachability")
    orchestration = _section("test-product")

    assert "não repita perguntas" in onboarding
    assert "partes dependentes" in reachability
    assert "siga o probe" in reachability
    assert "novo probe" in orchestration
    assert "reparos válidos" in orchestration
    assert "estudo de reutilização permanece pendente" in orchestration


def test_fluxo_de_captura_e_diario_estao_documentados() -> None:
    onboarding = _section("onboard-product")
    reference = (ROOT / "docs/reference/knowledge.md").read_text(encoding="utf-8")

    for command in ("knowledge capture", "knowledge validate", "knowledge diff"):
        assert command in onboarding
    for phrase in (
        "sem sobrescrever ou ativar",
        "não existe comando de promoção",
        "mudança a→b→a",
        "inclusive em outro estágio",
        "mesmo 201 pode ficar não testado",
    ):
        assert phrase in reference.lower()


def test_novos_textos_nao_vazam_termos_dos_casos() -> None:
    paths = [
        ROOT / "docs/reference/knowledge.md",
        *(ROOT / ".claude/skills" / n / "SKILL.md" for n in SKILLS),
    ]
    terms = []
    for case in (ROOT / "evals/cases").glob("*/case.yml"):
        terms.extend(yaml.safe_load(case.read_text(encoding="utf-8")).get("leak_terms", []))
    assert terms
    leaks = [
        f"{path.relative_to(ROOT)}: {term}"
        for path in paths
        for term in terms
        if re.search(
            rf"(?<!\w){re.escape(str(term))}(?!\w)", path.read_text(encoding="utf-8"), re.I
        )
    ]
    assert not leaks
