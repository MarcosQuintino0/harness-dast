"""Teste independente da exportação de conteúdo livre em comentários YAML."""

from contextlib import suppress
from pathlib import Path

from evals.runner.cases import EvalError
from evals.runner.reuse import export_reuse
from tests.unit.evals.test_reuse import _source


def test_v19_independent_export_never_persists_bearer_in_comment(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    source = _source(repo, out)
    marker = "synthetic-secret-12345"
    source.write_text(
        source.read_text(encoding="utf-8") + f"\n# Authorization: Bearer {marker}\n",
        encoding="utf-8",
    )
    package = tmp_path / "package"

    with suppress(EvalError):
        export_reuse(out, package)

    assert all(
        marker not in p.read_text(encoding="utf-8") for p in package.rglob("*") if p.is_file()
    )
