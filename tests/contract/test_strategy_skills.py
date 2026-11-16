"""A orientação de estratégia conserva as fronteiras da autorização."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude/skills/onboard-product/SKILL.md"


def test_onboarding_explica_classes_e_limites_da_estrategia() -> None:
    text = SKILL.read_text(encoding="utf-8").lower()
    strategy = text.split("a estratégia é opcional", 1)[1]

    for phrase in (
        "automática",
        "pendente de revisão",
        "decisão humana",
        "observação não concede permissão",
        "não enviam tráfego",
        "nem aprovam o perfil",
        "não sei / não está na carta",
    ):
        assert phrase in strategy


def test_onboarding_nao_ensina_vocabulario_de_produto_do_laboratorio() -> None:
    text = SKILL.read_text(encoding="utf-8").casefold()

    for term in ("clínica piloto", "clinica-piloto", "vampi", "paciente", "médico"):
        assert term not in text
