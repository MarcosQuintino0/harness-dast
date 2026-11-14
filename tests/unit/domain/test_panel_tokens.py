"""Os tokens embutidos nas páginas não podem divergir do `tokens.css` do desenho."""

import re
from pathlib import Path

from harness_dast.domain.panel_style import COMPONENTS_CSS, STYLE
from harness_dast.domain.panel_tokens import TOKENS_CSS

DESIGN = Path(__file__).parents[3] / "docs" / "design" / "execution-panel" / "tokens.css"


def _declarations(css: str) -> set[tuple[str, str]]:
    return {
        (name, " ".join(value.split()))
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", css)
    }


def test_embedded_tokens_are_identical_to_the_design_file() -> None:
    design = DESIGN.read_text(encoding="utf-8").replace("\r\n", "\n")

    assert design == TOKENS_CSS


def test_every_token_declaration_of_the_design_is_in_the_module() -> None:
    design = DESIGN.read_text(encoding="utf-8")

    assert _declarations(design)
    assert _declarations(design) == _declarations(TOKENS_CSS)


def test_style_is_the_tokens_followed_by_the_component_rules() -> None:
    assert STYLE == TOKENS_CSS + COMPONENTS_CSS


def test_components_take_their_colours_from_the_tokens_only() -> None:
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", COMPONENTS_CSS)
    assert "var(--color-surface)" in COMPONENTS_CSS


def test_dark_is_the_default_and_light_follows_the_device() -> None:
    assert "color-scheme: dark" in TOKENS_CSS
    assert "@media (prefers-color-scheme: light)" in TOKENS_CSS
    assert ':root:not([data-theme="dark"])' in TOKENS_CSS
    assert "@media (prefers-reduced-motion: reduce)" in TOKENS_CSS


def test_style_has_no_external_resource() -> None:
    assert not re.search(r"(?i)https?://|@import|url\(", STYLE)
