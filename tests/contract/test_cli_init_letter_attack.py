"""Contrato do `init --from-letter` com as chaves `attack.*` da V1.12 (ADR 0096)."""

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

QUOTE = "Autorizamos esta capacidade no ambiente de teste."


def _init(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], attack: dict[str, Any]
) -> tuple[int, dict[str, Any], Path]:
    data = valid_letter_data()
    data["attack"] = attack
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


def test_a_letter_with_the_keys_generates_the_blocks_and_the_warnings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    attack = {
        "pacing": answer("proxy", "pessoa"),
        "oast": answer(True, "carta", QUOTE),
        "inventory": answer(True, "carta", QUOTE),
    }

    code, envelope, products = _init(tmp_path, capsys, attack)

    assert code == ExitCode.OK
    blocks = envelope["data"]["generated_blocks"]
    assert {"scan.pacing", "scan.oast", "extra_checks"} <= set(blocks)
    warnings = envelope["data"]["warnings"]
    assert [w["field"] for w in warnings if w["code"] == "ATTACK_FLAG_AUTHORIZED"] == [
        "attack.oast",
        "attack.inventory",
    ]
    written = (products / "demo" / "target.yml").read_text(encoding="utf-8")
    assert 'pacing: "proxy"' in written
    assert "oast: true" in written
    assert "inventory: true" in written


def test_a_flag_without_the_letter_creates_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, products = _init(
        tmp_path, capsys, {"allow_rate_tests": answer(True, "pessoa", QUOTE)}
    )

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "LETTER_REJECTED"
    assert {i["field"]: i["code"] for i in envelope["data"]["issues"]} == {
        "attack.allow_rate_tests": "ATTACK_FLAG_NEEDS_LETTER"
    }
    assert list(products.iterdir()) == []


def test_a_letter_without_the_keys_generates_none_of_the_new_blocks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, products = _init(tmp_path, capsys, {})

    assert code == ExitCode.OK
    assert not {"scan.pacing", "scan.inject_headers", "scan.oast", "extra_checks"} & set(
        envelope["data"]["generated_blocks"]
    )
    written = (products / "demo" / "target.yml").read_text(encoding="utf-8")
    assert "extra_checks" not in written
    assert "pacing" not in written
