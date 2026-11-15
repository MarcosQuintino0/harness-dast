"""Contrato do `init --from-letter` com `attack.include_outcomes` (ADR 0050)."""

from pathlib import Path
from typing import Any

import pytest

from harness_dast.domain.errors import ExitCode
from tests.contract.test_cli_init_letter import (
    _isolated_env,  # noqa: F401 - fixture autouse do módulo da carta
    _letter_file,
    _products,
    _run_json,
)
from tests.fakes.letter_data import answer, valid_letter_data

pytestmark = pytest.mark.contract


def _init(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], outcomes: Any
) -> tuple[int, dict[str, Any], Path]:
    data = valid_letter_data()
    data["attack"] = {"include_outcomes": outcomes}
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
    return code, envelope, products


def test_a_letter_with_the_list_generates_the_block_and_the_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, products = _init(tmp_path, capsys, answer(["not_found", "conflict"], "pessoa"))

    assert code == ExitCode.OK
    assert "scan.include_outcomes" in envelope["data"]["generated_blocks"]
    assert "OUTCOMES_ATTACK_EXTENDED" in [w["code"] for w in envelope["data"]["warnings"]]
    written = (products / "demo" / "target.yml").read_text(encoding="utf-8")
    assert "include_outcomes" in written


def test_a_letter_with_an_invalid_class_creates_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, products = _init(tmp_path, capsys, answer(["server_error"]))

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "LETTER_REJECTED"
    assert {i["field"]: i["code"] for i in envelope["data"]["issues"]} == {
        "attack.include_outcomes": "INVALID_VALUE"
    }
    assert list(products.iterdir()) == []
