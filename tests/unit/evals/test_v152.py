"""Regressões da régua para sinais e permissões da carta."""

import copy
import json
from pathlib import Path

import pytest

from evals.runner.cases import load_case, load_round_case
from evals.runner.checks_findings import flaw_status, read_findings
from evals.runner.checks_profile import profile_checks
from evals.runner.models import Flaw, Matcher
from tests.unit.evals.support import CASES, GOOD_PROFILE, make_round, write_json


def test_findings_de_quatro_fontes_sao_lidos_e_casados_por_operacao(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    rows = [
        {"fingerprint": "f", "title": "SQL Injection"},
        {"fingerprint": "a", "technique": "authz_horizontal"},
        {"fingerprint": "s", "category": "stack_trace_java", "operation_id": "busca"},
        {"fingerprint": "n", "technique": "input_server_error", "operation_id": "busca"},
    ]
    write_json(
        trace / "runs/r/findings.json",
        {
            "findings": rows[:1],
            "authz": {"findings": rows[1:2]},
            "proxy_signals": {"findings": rows[2:3]},
            "negative": {"findings": rows[3:]},
        },
    )
    found = read_findings(trace)
    assert len(found) == 4
    for matcher in (
        Matcher(titles=("SQL Injection",)),
        Matcher(technique="authz_horizontal"),
        Matcher(category="stack_trace_java", operation_id="busca"),
        Matcher(technique="input_server_error", operation_id="busca"),
    ):
        flaw = Flaw(id="x", title="x", detectable=True, match=matcher)
        assert flaw_status(flaw, found) == "achada"
    assert (
        flaw_status(
            Flaw(
                id="x",
                title="x",
                detectable=True,
                match=Matcher(category="stack_trace_java", operation_id="outra"),
            ),
            found,
        )
        == "nao achada"
    )


@pytest.mark.parametrize(
    ("block", "field", "value"),
    [
        ("authz", "allow_writes", True),
        ("negative", "allow_writes", True),
        ("scan", "allow_upload_scan", True),
        ("scan", "include_outcomes", ["not_found"]),
    ],
)
def test_permissao_sem_carta_e_alargamento(block: str, field: str, value: object) -> None:
    profile = copy.deepcopy(GOOD_PROFILE)
    profile[block] = {field: value}
    checks = profile_checks(profile, load_case("mini", CASES))
    assert next(c for c in checks if c.id == "attack_permissions").passed is False


def test_caso_fica_lacrado_quando_fonte_muda(repo: Path, out: Path, tmp_path: Path) -> None:
    dirs = make_round(repo, out)
    original = load_round_case(dirs, "mini", tmp_path)
    assert original == load_case("mini", CASES)
    document = json.loads((dirs.sealed / "case.json").read_text(encoding="utf-8"))
    document["expected"]["allow_authz_writes"] = True
    (dirs.sealed / "case.json").write_text(json.dumps(document), encoding="utf-8")
    assert load_round_case(dirs, "mini", tmp_path).expected.allow_authz_writes


def test_nota_arquivada_recalculada_com_gabarito_historico(tmp_path: Path) -> None:
    """Reconstitui o wide de 14/11; o lacre de segredos não consta no arquivo sanitizado."""
    import shutil

    from evals.runner.cli import main

    archive = Path("evals/results/2026-11-14-clinica-piloto-terra61-medium-wide/attempts/02-main")
    out = tmp_path / "round"
    shutil.copytree(archive / "trace", out / "trace")
    shutil.move(out / "trace/executions", out / "trace/runs")
    shutil.copy2(archive / "transcript.jsonl", out / "transcript.jsonl")
    for file in (out / "trace").rglob("*.md.txt"):
        shutil.copy2(file, file.with_suffix(""))
    sealed = out / "sealed"
    sealed.mkdir()
    (sealed / "mode.json").write_text(
        '{"case":"clinica-piloto","mode":"vulnerable"}', encoding="utf-8"
    )
    case_file = Path("evals/cases/clinica-piloto-historico-terra-wide.yml")
    assert (
        main(
            [
                "score",
                "--out",
                str(out),
                "--case-file",
                str(case_file),
                "--tokens",
                "8023944",
                "--duration-seconds",
                "1777",
            ]
        )
        == 0
    )
    result = json.loads((out / "score.json").read_text(encoding="utf-8"))
    assert result["case_source"]["path"] == str(case_file)
    assert len(result["case_source"]["sha256"]) == 64
    saved = json.loads((archive / "score.json").read_text(encoding="utf-8"))
    assert result["grade"] == saved["grade"] == 7.18
    assert [c["score"] for c in result["components"]] == [c["score"] for c in saved["components"]]
    security = result["components"][0]
    assert next(c for c in security["checks"] if c["id"] == "no_secrets")["passed"] is None


def test_permissoes_sao_aceitas_quando_a_carta_autoriza() -> None:
    case = load_case("clinica-piloto")
    profile = copy.deepcopy(GOOD_PROFILE)
    profile.update(
        {
            "authz": {"allow_writes": True},
            "negative": {"allow_writes": True},
            "scan": {"include_outcomes": ["not_found"]},
        }
    )
    check = next(c for c in profile_checks(profile, case) if c.id == "attack_permissions")
    assert check.passed is True


def test_lista_malformada_de_outcomes_e_recusada() -> None:
    profile = copy.deepcopy(GOOD_PROFILE)
    profile["scan"] = {"include_outcomes": [{"invalido": True}]}
    check = next(
        c for c in profile_checks(profile, load_case("mini", CASES)) if c.id == "attack_permissions"
    )
    assert check.passed is False


def test_carta_explicita_as_permissoes_esperadas() -> None:
    text = Path("evals/cases/clinica-piloto/authorization.md").read_text(encoding="utf-8")
    assert "AMPLO" in text
    assert "escrita do teste de autoriza\u00e7\u00e3o entre contas" in text
    assert "escrita do teste de valores proibidos" in text
    assert "not_found" in text
    assert "listagem de documentos" in text


@pytest.mark.parametrize("block", ["authz", "negative", "scan"])
@pytest.mark.parametrize("value", [None, "texto", [], 1])
def test_bloco_de_ataque_malformado_e_recusado(block: str, value: object) -> None:
    profile = copy.deepcopy(GOOD_PROFILE)
    profile[block] = value
    check = next(
        c
        for c in profile_checks(profile, load_case("clinica-piloto"))
        if c.id == "attack_permissions"
    )
    assert check.passed is False
    assert block in check.detail


@pytest.mark.parametrize(
    ("block", "field"),
    [("authz", "allow_writes"), ("negative", "allow_writes"), ("scan", "allow_upload_scan")],
)
@pytest.mark.parametrize("value", [None, "true", 1, [], {}])
def test_flag_malformada_e_recusada_mesmo_quando_autorizada(
    block: str, field: str, value: object
) -> None:
    case = load_case("clinica-piloto")
    case = case.model_copy(
        update={"expected": case.expected.model_copy(update={"allow_upload_scan": True})}
    )
    profile = copy.deepcopy(GOOD_PROFILE)
    profile[block] = {field: value}
    check = next(c for c in profile_checks(profile, case) if c.id == "attack_permissions")
    assert check.passed is False
    assert f"{block}.{field}" in check.detail


def test_blocos_de_ataque_ausentes_sao_permitidos() -> None:
    check = next(
        c
        for c in profile_checks(GOOD_PROFILE, load_case("mini", CASES))
        if c.id == "attack_permissions"
    )
    assert check.passed is True


def test_rodada_antiga_exige_gabarito_explicito(tmp_path: Path) -> None:
    from evals.runner.cases import EvalError, RoundDirs

    with pytest.raises(EvalError, match="--case-file"):
        load_round_case(RoundDirs(tmp_path), "clinica-piloto")


def test_case_file_nao_pode_substituir_lacre(repo: Path, out: Path) -> None:
    from evals.runner.cases import EvalError

    dirs = make_round(repo, out)
    with pytest.raises(EvalError, match="nao substitua"):
        load_round_case(dirs, "mini", CASES, case_file=CASES / "mini/case.yml")


def test_case_file_de_outro_caso_e_recusado(tmp_path: Path) -> None:
    from evals.runner.cases import EvalError, RoundDirs

    with pytest.raises(EvalError, match="nao da rodada"):
        load_round_case(RoundDirs(tmp_path), "outro", case_file=CASES / "mini/case.yml")


def test_cli_recusa_rodada_antiga_sem_gabarito(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from evals.runner.cli import main

    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "mode.json").write_text(
        '{"case":"clinica-piloto","mode":"vulnerable"}', encoding="utf-8"
    )
    assert main(["score", "--out", str(tmp_path)]) == 2
    assert "--case-file" in capsys.readouterr().err
    assert not (tmp_path / "score.json").exists()
