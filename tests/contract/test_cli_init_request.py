"""Contrato de `hdast init --from-letter` com a carta `kind: request` (ADR 0120)."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from harness_dast.cli import composition
from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode
from tests.fakes.clock import FixedClock, utc
from tests.fakes.letter_data import answer, request_letter_data
from tests.fakes.profile_data import dump_yaml

pytestmark = pytest.mark.contract

LAB_OPENAPI = Path(__file__).parents[2] / "lab" / "pilot" / "product-profile" / "openapi.json"
PRODUCT = "clinica-piloto"
UNKNOWN = {"source": "desconhecido"}
# O OpenAPI do laboratório não tem caminho perigoso, então `scope.deny_paths` não é sugerido.
EXPECTED_APPLIED = {
    "scope.allow",
    "scope.path_mode",
    "environment.name",
    "authorization.reference",
    "authorization.valid_until",
    "authorization.windows",
    "limits.requests_per_second",
    "limits.max_duration_minutes",
    "limits.zap_threads_per_host",
    "auth.login_max_per_minute",
    "scan.strength",
    "scan.include_outcomes",
    "scan.pacing",
    "scan.inject_headers",
    "scan.oast",
    "extra_checks.allow_rate_tests",
    "extra_checks.experimental_rules",
    "extra_checks.inventory",
    "extra_checks.nuclei",
    "extra_checks.nuclei_login",
}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(composition, "SystemClock", lambda: FixedClock(utc(2026, 11, 18)))
    for name in ("HDAST_LOG_LEVEL", "HDAST_PRODUCTS_DIR", "HDAST_ZAP_API_KEY", "TZ"):
        monkeypatch.delenv(name, raising=False)


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any]]:
    code = run_app(build_app(), ["--json", *args])
    return code, json.loads(capsys.readouterr().out)


def _letter_data() -> dict[str, Any]:
    data = request_letter_data(PRODUCT, "http://clinica-piloto:8080")
    data["auth"]["token_path"] = answer("/api/auth/login", "pessoa")
    return data


def _setup(tmp_path: Path, data: dict[str, Any] | None = None) -> tuple[Path, Path]:
    """Pasta da carta (com o OpenAPI ao lado) e pasta de produtos vazia."""
    folder = tmp_path / "carta"
    folder.mkdir()
    shutil.copy(LAB_OPENAPI, folder / "openapi.json")
    letter = folder / "carta.yml"
    letter.write_text(dump_yaml(data or _letter_data()), encoding="utf-8")
    products = tmp_path / "produtos"
    products.mkdir()
    return letter, products


def _init(
    capsys: pytest.CaptureFixture[str], letter: Path, products: Path, *extra: str
) -> tuple[int, dict[str, Any]]:
    return _run(
        capsys,
        "init",
        PRODUCT,
        "--from-letter",
        str(letter),
        "--products-dir",
        str(products),
        *extra,
    )


def _target(products: Path) -> str:
    return (products / PRODUCT / "target.yml").read_text(encoding="utf-8")


def test_init_cria_o_produto_com_cada_padrao_em_aviso_e_cabecalho_quando_a_carta_e_minima(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    letter, products = _setup(tmp_path)

    code, envelope = _init(capsys, letter, products)

    assert code == ExitCode.OK
    assert envelope["data"]["ready"] is True
    applied = {
        w["field"] for w in envelope["data"]["warnings"] if w["code"] == "REQUEST_DEFAULT_APPLIED"
    }
    text = _target(products)
    assert applied == EXPECTED_APPLIED
    for field in applied:
        assert f"# Padrão do pedido mínimo: {field} = " in text
    assert "seg-dom 00:00-24:00 America/Sao_Paulo" in text
    assert "valid_until: 2026-12-18" in text


def test_perfil_do_pedido_minimo_passa_no_profile_validate_quando_o_openapi_esta_na_pasta(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    letter, products = _setup(tmp_path)
    _init(capsys, letter, products)
    shutil.copy(LAB_OPENAPI, products / PRODUCT / "openapi.json")

    code, envelope = _run(capsys, "profile", "validate", PRODUCT, "--products-dir", str(products))

    assert code == ExitCode.OK
    assert envelope["data"]["runnable"] is True
    assert envelope["data"]["issues"] == []


def test_init_usa_o_fuso_da_variavel_tz_quando_ela_e_valida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TZ", "UTC")
    letter, products = _setup(tmp_path)

    _init(capsys, letter, products)

    assert "seg-dom 00:00-24:00 UTC" in _target(products)


def test_init_deixa_delete_fora_quando_a_carta_e_minima(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    letter, products = _setup(tmp_path)

    _init(capsys, letter, products)

    assert '"DELETE"' not in _target(products)


def test_init_inclui_delete_quando_a_pessoa_o_pede(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _letter_data()
    data["scope"] = {"allow_delete": answer(True, "pessoa")}
    letter, products = _setup(tmp_path, data)

    code, envelope = _init(capsys, letter, products)

    assert code == ExitCode.OK
    assert '"DELETE"' in _target(products)
    assert "DELETE_AUTHORIZED" in {w["code"] for w in envelope["data"]["warnings"]}


@pytest.mark.parametrize("reply", [answer(False, "pessoa"), UNKNOWN])
def test_init_nada_cria_quando_a_pergunta_1_e_nao_ou_desconhecida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], reply: dict[str, Any]
) -> None:
    data = _letter_data()
    data["gates"]["synthetic_data"] = reply
    letter, products = _setup(tmp_path, data)

    code, envelope = _init(capsys, letter, products)

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert not (products / PRODUCT).exists()
    assert [i["field"] for i in envelope["data"]["issues"]] == ["gates.synthetic_data"]


def test_init_nada_cria_quando_a_pergunta_2_e_desconhecida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _letter_data()
    data["environment"]["base_url"] = UNKNOWN
    letter, products = _setup(tmp_path, data)

    code, envelope = _init(capsys, letter, products)

    assert code == ExitCode.USAGE
    assert not (products / PRODUCT).exists()
    assert [i["code"] for i in envelope["data"]["issues"]] == ["UNKNOWN"]


def test_init_nada_cria_e_diz_o_motivo_quando_o_openapi_nao_esta_ao_lado_da_carta(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    letter, products = _setup(tmp_path)
    (letter.parent / "openapi.json").unlink()

    code, envelope = _init(capsys, letter, products)

    assert code == ExitCode.USAGE
    assert not (products / PRODUCT).exists()
    assert [i["code"] for i in envelope["data"]["issues"]] == ["OPENAPI_UNREADABLE"]


def test_check_confere_o_pedido_minimo_sem_criar_nada(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    letter, products = _setup(tmp_path)

    code, envelope = _init(capsys, letter, products, "--check")

    assert code == ExitCode.OK
    assert envelope["data"]["ready"] is True
    assert not (products / PRODUCT).exists()
    assert len(envelope["data"]["warnings"]) > len(EXPECTED_APPLIED)


def test_init_mostra_os_avisos_dos_padroes_em_modo_humano(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    letter, products = _setup(tmp_path)

    code = run_app(
        build_app(),
        ["init", PRODUCT, "--from-letter", str(letter), "--products-dir", str(products)],
    )

    out = capsys.readouterr().out
    assert code == ExitCode.OK
    assert "Padrão do pedido mínimo: limits.requests_per_second = 10" in out
