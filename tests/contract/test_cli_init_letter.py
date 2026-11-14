"""Contrato de `hdast init --from-letter` e `--check` (ADR 0036): envelope e falha fechada."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from harness_dast.cli import composition
from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode
from tests.fakes.clock import FixedClock, utc
from tests.fakes.letter_data import answer, valid_letter_data
from tests.fakes.profile_data import dump_yaml

pytestmark = pytest.mark.contract

FIXTURES = Path(__file__).parents[1] / "fixtures" / "letter"
LAB_LETTER = FIXTURES / "clinica-piloto.carta.yml"
LAB_OPENAPI = Path(__file__).parents[2] / "lab" / "pilot" / "product-profile" / "openapi.json"
LAB_GOLDEN = FIXTURES / "clinica-piloto.target.golden.yml"
SECRET = "SenhaLiteral-Nao-Pode-Vazar-5"  # noqa: S105 - sentinela para provar que não vaza

LETTER_KEYS = {
    "product",
    "ready",
    "check",
    "generated_blocks",
    "issues",
    "warnings",
    "example_data",
}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # O relógio é fixo: a validade da carta não pode depender do dia em que o teste roda.
    monkeypatch.setattr(composition, "SystemClock", lambda: FixedClock(utc(2026, 11, 14)))
    for name in ("HDAST_LOG_LEVEL", "HDAST_PRODUCTS_DIR", "HDAST_ZAP_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = run_app(build_app(), list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _run_json(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any]]:
    code, out, _ = _run(capsys, "--json", *args)
    return code, json.loads(out)


def _letter_file(tmp_path: Path, data: dict[str, Any], name: str = "carta.yml") -> Path:
    path = tmp_path / name
    path.write_text(dump_yaml(data), encoding="utf-8")
    return path


def _products(tmp_path: Path) -> Path:
    products = tmp_path / "produtos"
    products.mkdir()
    return products


def test_init_from_letter_creates_the_product_with_the_golden_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = _products(tmp_path)

    code, envelope = _run_json(
        capsys,
        "init",
        "clinica-piloto",
        "--from-letter",
        str(LAB_LETTER),
        "--products-dir",
        str(products),
    )

    assert code == ExitCode.OK
    assert envelope["ok"] is True
    assert set(envelope["data"]) == LETTER_KEYS | {"directory", "files"}
    assert envelope["data"]["ready"] is True
    assert envelope["data"]["check"] is False
    assert envelope["data"]["issues"] == []
    assert "scope" in envelope["data"]["generated_blocks"]
    assert "target.yml" in envelope["data"]["files"]
    written = (products / "clinica-piloto" / "target.yml").read_text(encoding="utf-8")
    assert written == LAB_GOLDEN.read_text(encoding="utf-8")


def test_init_from_letter_returns_the_example_data_for_the_agent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = _run_json(
        capsys,
        "init",
        "clinica-piloto",
        "--from-letter",
        str(LAB_LETTER),
        "--products-dir",
        str(_products(tmp_path)),
    )

    assert code == ExitCode.OK
    assert envelope["data"]["example_data"][0]["field"] == "nome"


def test_generated_profile_passes_profile_validate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = _products(tmp_path)
    _run(
        capsys,
        "init",
        "clinica-piloto",
        "--from-letter",
        str(LAB_LETTER),
        "--products-dir",
        str(products),
    )
    # O OpenAPI vem do produto, não da carta: sem ele a única pendência seria FILE_MISSING.
    shutil.copy(LAB_OPENAPI, products / "clinica-piloto" / "openapi.json")

    code, envelope = _run_json(
        capsys, "profile", "validate", "clinica-piloto", "--products-dir", str(products)
    )

    assert code == ExitCode.OK
    assert envelope["data"]["runnable"] is True
    assert envelope["data"]["issues"] == []
    assert [a["alias"] for a in envelope["data"]["accounts"]] == [
        "admin_a",
        "paciente_a",
        "paciente_b",
    ]


def test_init_from_letter_is_byte_identical_when_run_twice_in_different_folders(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()

    for products in (first, second):
        code, _ = _run_json(
            capsys,
            "init",
            "clinica-piloto",
            "--from-letter",
            str(LAB_LETTER),
            "--products-dir",
            str(products),
        )
        assert code == ExitCode.OK

    assert (first / "clinica-piloto" / "target.yml").read_bytes() == (
        second / "clinica-piloto" / "target.yml"
    ).read_bytes()


def test_init_from_letter_prints_a_readable_summary_in_human_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(
        capsys,
        "init",
        "clinica-piloto",
        "--from-letter",
        str(LAB_LETTER),
        "--products-dir",
        str(_products(tmp_path)),
    )

    assert code == ExitCode.OK
    assert "Produto clinica-piloto criado" in out
    assert "hdast profile validate clinica-piloto" in out
    assert err == ""


# ---------------------------------------------------------------- --check


def test_check_confirms_a_ready_letter_without_creating_anything(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = _products(tmp_path)

    code, envelope = _run_json(
        capsys,
        "init",
        "clinica-piloto",
        "--from-letter",
        str(LAB_LETTER),
        "--check",
        "--products-dir",
        str(products),
    )

    assert code == ExitCode.OK
    assert set(envelope["data"]) == LETTER_KEYS
    assert envelope["data"]["ready"] is True
    assert envelope["data"]["check"] is True
    assert list(products.iterdir()) == []


def test_check_lists_every_missing_field_by_path_in_the_json_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_letter_data()
    del data["limits"]["requests_per_second"]
    data["authorization"]["reference"] = {"source": "desconhecido"}
    data["environment"]["base_url"] = answer("https://api.exemplo.com.br")
    letter = _letter_file(tmp_path, data)
    products = _products(tmp_path)

    code, envelope = _run_json(
        capsys,
        "init",
        "demo",
        "--from-letter",
        str(letter),
        "--check",
        "--products-dir",
        str(products),
    )

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "LETTER_REJECTED"
    assert envelope["data"]["ready"] is False
    issues = {i["field"]: i["code"] for i in envelope["data"]["issues"]}
    assert issues == {
        "limits.requests_per_second": "MISSING",
        "authorization.reference": "UNKNOWN",
        "environment.base_url": "PLACEHOLDER",
    }
    assert all(i["message"] for i in envelope["data"]["issues"])
    assert list(products.iterdir()) == []


def test_check_without_from_letter_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = _products(tmp_path)

    code, envelope = _run_json(capsys, "init", "demo", "--check", "--products-dir", str(products))

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert list(products.iterdir()) == []


# ---------------------------------------------------------------- falha fechada


def test_init_from_letter_creates_nothing_when_a_gate_is_answered_no(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_letter_data()
    data["gates"]["synthetic_data"] = answer(False)
    letter = _letter_file(tmp_path, data)
    products = _products(tmp_path)

    code, envelope = _run_json(
        capsys, "init", "demo", "--from-letter", str(letter), "--products-dir", str(products)
    )

    assert code == ExitCode.USAGE
    assert [i["code"] for i in envelope["data"]["issues"]] == ["GATE_DENIED"]
    assert list(products.iterdir()) == []


def test_init_from_letter_creates_nothing_when_wide_does_not_come_from_the_letter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_letter_data()
    data["scope"]["path_mode"] = answer("wide", "pessoa", "acho que pode")
    letter = _letter_file(tmp_path, data)
    products = _products(tmp_path)

    code, envelope = _run_json(
        capsys, "init", "demo", "--from-letter", str(letter), "--products-dir", str(products)
    )

    assert code == ExitCode.USAGE
    assert envelope["data"]["issues"][0]["code"] == "WIDE_NEEDS_LETTER"
    assert list(products.iterdir()) == []


def test_init_from_letter_human_mode_says_the_answer_comes_from_the_person(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_letter_data()
    del data["limits"]["requests_per_second"]
    letter = _letter_file(tmp_path, data)

    code, out, err = _run(
        capsys,
        "init",
        "demo",
        "--from-letter",
        str(letter),
        "--products-dir",
        str(_products(tmp_path)),
    )

    assert code == ExitCode.USAGE
    assert "1 pendência(s)" in out
    assert "limits.requests_per_second [MISSING]" in err
    assert "agente não preenche" in err


def test_init_from_letter_never_overwrites_an_existing_product(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = _products(tmp_path)
    (products / "demo").mkdir()
    (products / "demo" / "target.yml").write_text("meu trabalho", encoding="utf-8")
    letter = _letter_file(tmp_path, valid_letter_data())

    code, envelope = _run_json(
        capsys, "init", "demo", "--from-letter", str(letter), "--products-dir", str(products)
    )

    assert code == ExitCode.USAGE
    assert "já existe" in envelope["error"]["message"]
    assert (products / "demo" / "target.yml").read_text(encoding="utf-8") == "meu trabalho"


def test_init_from_letter_fails_when_the_letter_file_does_not_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = _run_json(
        capsys,
        "init",
        "demo",
        "--from-letter",
        str(tmp_path / "nao-existe.yml"),
        "--products-dir",
        str(_products(tmp_path)),
    )

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"


def test_init_from_letter_fails_when_the_letter_has_an_unknown_field(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_letter_data()
    data["scope"]["allow_all"] = answer(True)
    letter = _letter_file(tmp_path, data)

    code, envelope = _run_json(
        capsys,
        "init",
        "demo",
        "--from-letter",
        str(letter),
        "--products-dir",
        str(_products(tmp_path)),
    )

    assert code == ExitCode.USAGE
    assert "scope.allow_all" in envelope["error"]["message"]


def test_init_from_letter_fails_when_the_letter_is_malformed_yaml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    letter = tmp_path / "carta.yml"
    letter.write_text("gates: [\n", encoding="utf-8")

    code, envelope = _run_json(
        capsys,
        "init",
        "demo",
        "--from-letter",
        str(letter),
        "--products-dir",
        str(_products(tmp_path)),
    )

    assert code == ExitCode.USAGE
    assert "YAML" in envelope["error"]["message"]


@pytest.mark.parametrize("json_mode", [True, False])
def test_init_from_letter_never_echoes_a_literal_secret_found_in_the_letter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], json_mode: bool
) -> None:
    data = valid_letter_data()
    data["auth"]["accounts"]["value"][0]["password"] = {"secret_ref": SECRET}
    letter = _letter_file(tmp_path, data)
    flags = ["--json"] if json_mode else []

    code, out, err = _run(
        capsys,
        *flags,
        "init",
        "demo",
        "--from-letter",
        str(letter),
        "--products-dir",
        str(_products(tmp_path)),
    )

    assert code == ExitCode.USAGE
    assert SECRET not in out
    assert SECRET not in err
    assert "auth.accounts[0].password.secret_ref" in out + err


def test_init_from_letter_refuses_the_letter_of_another_product(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = _run_json(
        capsys,
        "init",
        "outro-produto",
        "--from-letter",
        str(LAB_LETTER),
        "--products-dir",
        str(_products(tmp_path)),
    )

    assert code == ExitCode.USAGE
    assert envelope["data"]["issues"][0]["code"] == "PRODUCT_MISMATCH"


def test_plain_init_keeps_its_original_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = _run_json(capsys, "init", "demo", "--products-dir", str(tmp_path))

    assert code == ExitCode.OK
    assert set(envelope["data"]) == {"product", "directory", "files"}


def test_check_refuses_a_letter_with_an_expired_authorization_with_its_own_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_letter_data()
    data["authorization"]["valid_until"] = answer("2026-11-13")
    letter = _letter_file(tmp_path, data)

    code, envelope = _run_json(capsys, "init", "demo", "--from-letter", str(letter), "--check")

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["data"]["ready"] is False
    assert [(i["field"], i["code"]) for i in envelope["data"]["issues"]] == [
        ("authorization.valid_until", "AUTHORIZATION_EXPIRED")
    ]


def test_init_from_an_expired_letter_creates_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_letter_data()
    data["authorization"]["valid_until"] = answer("2026-11-13")
    products = _products(tmp_path)

    code, _ = _run_json(
        capsys,
        "init",
        "demo",
        "--from-letter",
        str(_letter_file(tmp_path, data)),
        "--products-dir",
        str(products),
    )

    assert code == ExitCode.USAGE
    assert list(products.iterdir()) == []


def test_warnings_go_in_the_envelope_and_do_not_block_or_change_the_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = valid_letter_data()
    data["scope"]["deny_paths"] = answer([])
    letter = _letter_file(tmp_path, data)

    code, envelope = _run_json(capsys, "init", "demo", "--from-letter", str(letter), "--check")

    assert code == ExitCode.OK
    assert envelope["data"]["ready"] is True
    assert envelope["data"]["issues"] == []
    assert {w["code"] for w in envelope["data"]["warnings"]} == {
        "DENY_PATHS_EMPTY",
        "VALIDITY_OVER_ONE_YEAR",
    }
    assert all({"field", "code", "message"} == set(w) for w in envelope["data"]["warnings"])


def test_init_from_letter_writes_allow_writes_and_warns_only_when_the_letter_authorizes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = _products(tmp_path)
    data = valid_letter_data("demo")
    data["attack"] = {
        "allow_authz_writes": answer(True, "carta", "A carta autoriza escrita do teste.")
    }
    letter = _letter_file(tmp_path, data)

    code, envelope = _run_json(
        capsys, "init", "demo", "--from-letter", str(letter), "--products-dir", str(products)
    )

    assert code == ExitCode.OK
    assert "authz.allow_writes" in envelope["data"]["generated_blocks"]
    assert "AUTHZ_WRITES_AUTHORIZED" in [w["code"] for w in envelope["data"]["warnings"]]
    target = (products / "demo" / "target.yml").read_text(encoding="utf-8")
    assert "authz:\n  allow_writes: true\n" in target


def test_init_from_letter_refuses_writes_answered_by_a_person_without_the_letter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = _products(tmp_path)
    data = valid_letter_data("demo")
    data["attack"] = {"allow_authz_writes": answer(True, "pessoa")}
    letter = _letter_file(tmp_path, data)

    code, envelope = _run_json(
        capsys, "init", "demo", "--from-letter", str(letter), "--products-dir", str(products)
    )

    assert code == ExitCode.USAGE
    assert [i["code"] for i in envelope["data"]["issues"]] == ["AUTHZ_WRITES_NEEDS_LETTER"]
    assert list(products.iterdir()) == []
