"""Contrato da carta para papéis compartilhados."""

from pathlib import Path

import pytest

from harness_dast.domain.errors import ExitCode
from tests.contract.test_cli_init_letter import (
    _isolated_env,  # noqa: F401 - fixture do contrato
    _letter_file,
    _products,
    _run_json,
)
from tests.fakes.letter_data import answer, valid_letter_data

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    ("source", "quote", "expected"),
    [
        ("carta", "Compartilham recursos", ExitCode.OK),
        ("pessoa", "Compartilham recursos", ExitCode.USAGE),
    ],
)
def test_init_requires_letter_and_copies_roles(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], source: str, quote: str, expected: int
) -> None:
    data = valid_letter_data()
    role = data["auth"]["accounts"]["value"][0]["role"]
    data["attack"] = {"authz_shared_roles": answer([role], source, quote)}
    products = _products(tmp_path)
    code, envelope = _run_json(
        capsys,
        "init",
        "demo",
        "--from-letter",
        str(_letter_file(tmp_path, data)),
        "--products-dir",
        str(products),
    )
    assert code == expected
    if expected == ExitCode.OK:
        assert "authz.shared_roles" in envelope["data"]["generated_blocks"]
        assert "shared_roles:" in (products / "demo" / "target.yml").read_text(encoding="utf-8")
    else:
        assert envelope["error"]["code"] == "LETTER_REJECTED"
        assert list(products.iterdir()) == []
