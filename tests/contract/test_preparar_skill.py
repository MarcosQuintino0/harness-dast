"""Contrato de fontes, permissões e limites da skill de preparação."""

import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "plugin" / "skills" / "preparar" / "SKILL.md"
SOURCES = frozenset(
    {
        "https://docs.astral.sh/uv/getting-started/installation/",
        "https://docs.docker.com/engine/install/",
        "https://docs.docker.com/desktop/setup/install/mac-install/",
        "https://github.com/<dono/repositório>/releases/download/v<versão>/"
        "harness_dast-<versão>-py3-none-any.whl",
    }
)


def test_preparar_lists_only_the_fixed_installation_sources() -> None:
    skill = SKILL.read_text(encoding="utf-8")

    assert set(re.findall(r"https?://[^\s)`]+", skill)) == SOURCES
    assert set(re.findall(r"winget install [^`]+", skill)) == {
        "winget install --id astral-sh.uv -e",
        "winget install --id Docker.DockerDesktop -e",
    }
    assert "uv tool install --python 3.12 <URL do wheel>" in skill
    assert "HDAST_RELEASE_REPOSITORY" in skill
    assert "MarcosQuintino0/harness-dast" in skill
    assert "hdast stack pull" in skill


def test_preparar_requires_explicit_permission_before_each_install() -> None:
    skill = SKILL.read_text(encoding="utf-8")

    permission = skill.index("Para **cada instalação**")
    consent = skill.index("aguarde o **sim explícito**", permission)
    execution = skill.index("só então peça a permissão do Claude Code", consent)
    assert "Nunca encadeie instalações" in skill
    assert execution < skill.index("winget install", execution)


def test_preparar_covers_the_four_installation_notices() -> None:
    skill = SKILL.read_text(encoding="utf-8")

    for notice in (
        "o Docker Desktop e o WSL 2 pedem administrador, e a janela de elevação é da pessoa",
        "Pode ser preciso reiniciar",
        "licença paga em empresa grande, e a TI precisa confirmar",
        "instalação bloqueada ou que precisa do WSL 2, entregue a lista para a TI",
    ):
        assert notice in skill


def test_preparar_stays_on_the_local_machine() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    commands = re.findall(r"`hdast ([^`]+)`", skill)
    forbidden = (
        r"\.env\b|(?:uv\s+run\s+)?hdast(?:\s+--json)?\s+(?:"
        r"setup|profile\s+approve|secret\s+(?:set|delete)|mutation\s+release|"
        r"finding\s+acknowledge|demo|cleanup|preflight|probe|scan|authz|negative|confirm|run)\b"
    )

    assert set(commands) == {"--version", "doctor", "stack pull"}
    assert not re.search(forbidden, skill, re.IGNORECASE)
