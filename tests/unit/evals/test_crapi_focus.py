"""Contratos do caso curto e da fronteira da cópia cega."""

import json
from pathlib import Path

import pytest
import yaml

from evals.runner.approve import approve
from evals.runner.cases import REPO_ROOT, EvalError, RoundDirs, load_case
from evals.runner.checks_profile import profile_checks
from evals.runner.prepare import prepare
from harness_dast.cli import composition
from harness_dast.cli.app import build_app, run_app
from tests.fakes.clock import FixedClock, utc


@pytest.fixture
def focus_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RoundDirs:
    monkeypatch.setattr(composition, "SystemClock", lambda: FixedClock(utc(2026, 11, 17)))
    out = tmp_path / "round"
    result = prepare("crapi-foco", "vulnerable", 7, out)
    assert not result.leaks
    return RoundDirs(out)


def _init(dirs: RoundDirs) -> Path:
    code = run_app(
        build_app(),
        [
            "--json",
            "init",
            "crapi",
            "--from-letter",
            str(dirs.workspace / "inputs/carta.yml"),
            "--products-dir",
            str(dirs.workspace / "products"),
        ],
    )
    assert code == 0
    return dirs.workspace / "products/crapi/target.yml"


def test_prepara_copia_sem_gabarito_quando_caso_foco(focus_round: RoundDirs) -> None:
    ws = focus_round.workspace
    assert (ws / "inputs/carta.yml").read_bytes() == (
        REPO_ROOT / "evals/cases/crapi-foco/carta.yml"
    ).read_bytes()
    assert (ws / "inputs/openapi.json").is_file()
    assert not (ws / "evals").exists()
    assert not (ws / "docs/adr").exists()
    assert not (ws / "lab/crapi/README.md").exists()
    assert not (ws / "lab/crapi/seed.py").exists()
    skills = {p.name for p in (ws / ".claude/skills").iterdir() if p.is_dir()}
    assert skills == {
        "onboard-product",
        "fix-reachability",
        "run-scan",
        "triage-findings",
        "test-product",
    }
    manifest = json.loads(
        (focus_round.sealed / "workspace-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["policy"] == "allowlist-v1"
    assert manifest["stage"] == "repository-copy"
    assert manifest["total_files"] == sum(manifest["roots"].values())


def test_ensaio_aprova_perfil_gerado_pela_carta(focus_round: RoundDirs) -> None:
    profile = _init(focus_round)
    data = yaml.safe_load(profile.read_text(encoding="utf-8"))
    assert data["scan"]["strength"] == "LOW"
    assert approve(focus_round.out).product == "crapi"


def test_ensaio_recusa_perfil_com_escopo_alargado(focus_round: RoundDirs) -> None:
    profile = _init(focus_round)
    data = yaml.safe_load(profile.read_text(encoding="utf-8"))
    data["scope"]["allow"][0]["paths"].append("/identity/api/**")
    profile.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(EvalError, match="alarga"):
        approve(focus_round.out)
    assert not (focus_round.state / "approvals").exists()


def test_ensaio_recusa_metodo_de_outra_regra(focus_round: RoundDirs) -> None:
    profile = _init(focus_round)
    data = yaml.safe_load(profile.read_text(encoding="utf-8"))
    data["scope"]["allow"][0]["methods"].append("GET")
    profile.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(EvalError, match="allow"):
        approve(focus_round.out)
    assert not (focus_round.state / "approvals").exists()


@pytest.mark.parametrize(
    ("change", "value"), [("host", "outro"), ("scheme", "https"), ("port", 81)]
)
def test_recusa_origem_fora_da_carta(change: str, value: object) -> None:
    case = load_case("crapi-foco")
    rule = case.expected.allow[0].model_dump()
    rule[change] = value
    check = next(c for c in profile_checks({"scope": {"allow": [rule]}}, case) if c.id == "allow")
    assert check.passed is False


def test_esquema_e_porta_omitidos_seguem_padrao_do_perfil() -> None:
    case = load_case("crapi-foco")
    rule = case.expected.allow[0].model_dump()
    del rule["port"]
    check = next(c for c in profile_checks({"scope": {"allow": [rule]}}, case) if c.id == "allow")
    assert check.passed is True
    del rule["scheme"]
    check = next(c for c in profile_checks({"scope": {"allow": [rule]}}, case) if c.id == "allow")
    assert check.passed is False
    expected = case.expected.allow[0].model_copy(update={"scheme": "https", "port": 443})
    case = case.model_copy(
        update={"expected": case.expected.model_copy(update={"allow": (expected,)})}
    )
    check = next(c for c in profile_checks({"scope": {"allow": [rule]}}, case) if c.id == "allow")
    assert check.passed is True


def test_aceita_pares_cobertos_por_regras_distintas() -> None:
    case = load_case("crapi-foco")
    rule = case.expected.allow[2].model_dump()
    rule["methods"] = ["GET", "PUT"]
    check = next(c for c in profile_checks({"scope": {"allow": [rule]}}, case) if c.id == "allow")
    assert check.passed is True


def test_listagem_de_veiculos_existe_no_contrato_e_na_carta() -> None:
    path = "/identity/api/v2/vehicle/vehicles"
    spec = json.loads((REPO_ROOT / "lab/crapi/openapi.json").read_text(encoding="utf-8"))
    assert spec["paths"][path]["get"]["operationId"] == "get_vehicles"
    letter = yaml.safe_load(
        (REPO_ROOT / "evals/cases/crapi-foco/carta.yml").read_text(encoding="utf-8")
    )
    assert any(
        path in r["paths"] and "GET" in r["methods"] for r in letter["scope"]["allow"]["value"]
    )
    assert "get" not in spec["paths"]["/identity/api/v2/user/videos"]
    assert not any(
        "/identity/api/v2/user/videos" in r["paths"] and "GET" in r["methods"]
        for r in letter["scope"]["allow"]["value"]
    )


def test_caso_declara_so_a_deteccao_provada_e_nenhum_prazo_medido() -> None:
    case = load_case("crapi-foco")
    assert {f.id for f in case.flaws} == {"C1", "C3", "C6", "C10", "C11", "C12", "C15"}
    assert {f.id for f in case.flaws if f.detectable} == {"C3", "C11", "C15"}
    assert case.budget.duration_seconds == 900


def test_carta_liga_as_capacidades_da_v1_12_com_frase_e_gera_o_perfil(
    focus_round: RoundDirs,
) -> None:
    data = yaml.safe_load(_init(focus_round).read_text(encoding="utf-8"))
    assert data["scan"]["pacing"] == "proxy"
    assert data["scan"]["inject_headers"] is True
    assert data["scan"]["oast"] is True
    assert data["extra_checks"] == {
        "allow_rate_tests": True,
        "experimental_rules": True,
        "inventory": True,
    }
    denied = data["scope"]["deny_paths"]
    assert "/identity/api/auth/v2/check-otp" not in denied
    assert "/identity/api/auth/v3/check-otp" in denied
