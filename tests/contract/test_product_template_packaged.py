"""O modelo de produto empacotado é igual ao do clone (ADR 0119: a CLI instalada cria produtos)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLONE = ROOT / "products" / "_template"
PACKAGED = ROOT / "src" / "harness_dast" / "product_template"


def _files(base: Path) -> dict[str, bytes]:
    return {
        path.relative_to(base).as_posix(): path.read_bytes().replace(b"\r\n", b"\n")
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def test_packaged_template_matches_the_clone_template() -> None:
    assert _files(PACKAGED) == _files(CLONE)
