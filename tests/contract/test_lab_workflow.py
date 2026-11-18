"""Confere o contrato do laboratório no GitHub sem iniciar contêineres."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_round import Piece

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/lab.yml"
LABEL_GATE = "contains(github.event.pull_request.labels.*.name, 'lab')"
pytestmark = pytest.mark.contract


@pytest.fixture
def workflow() -> dict[str, Any]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return list(job["steps"])


def _uses(job: dict[str, Any]) -> list[str]:
    return [str(step["uses"]) for step in _steps(job) if "uses" in step]


def test_workflow_restringe_disparos_quando_em_pull_request(workflow: dict[str, Any]) -> None:
    events = workflow["on"]

    assert set(events) == {"workflow_dispatch", "pull_request"}
    assert set(events["pull_request"]["types"]) == {"labeled", "synchronize"}
    nivel = events["workflow_dispatch"]["inputs"]["nivel"]
    assert nivel["options"] == ["fast", "prova", "regressao", "carga", "tudo"]
    assert nivel["default"] == "fast"


def test_workflow_so_roda_com_rotulo_quando_vem_de_pull_request(workflow: dict[str, Any]) -> None:
    jobs = workflow["jobs"]

    assert LABEL_GATE in jobs["planejar"]["if"]
    for name, job in jobs.items():
        if name != "planejar":
            assert "planejar" in job["needs"], f"{name} escapa do portão do rótulo"


def test_workflow_respeita_leitura_prazo_e_credenciais_quando_executa(
    workflow: dict[str, Any],
) -> None:
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "lab-${{ github.ref }}",
        "cancel-in-progress": True,
    }
    for name, job in workflow["jobs"].items():
        assert all(value == "read" for value in job.get("permissions", {}).values()), name
        assert isinstance(job["timeout-minutes"], int), name
        assert job["timeout-minutes"] > 0, name
        for step in _steps(job):
            if str(step.get("uses", "")).startswith("actions/checkout"):
                assert step["with"]["persist-credentials"] is False, name


def test_workflow_nao_usa_segredos_nem_versoes_soltas_quando_declara_passos(
    workflow: dict[str, Any],
) -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert not re.search(r"\bsecrets\b", text, re.IGNORECASE)
    assert "GITHUB_TOKEN" not in text
    for job in workflow["jobs"].values():
        for reference in _uses(job):
            assert re.search(r"@v\d+\.\d+\.\d+$", reference), reference


def test_planejar_gera_a_matriz_pelo_lab_round_quando_roda(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["planejar"]
    commands = " ".join(step.get("run", "") for step in _steps(job))

    assert "tests.integration.lab_round" in commands
    assert "--pedacos-json" in commands
    assert set(job["outputs"]) == {"matriz", "pedacos"}
    assert '"include"' in commands


def test_pedaco_usa_matriz_do_planejador_quando_distribui(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["pedaco"]
    strategy = job["strategy"]

    assert strategy["matrix"] == "${{ fromJSON(needs.planejar.outputs.matriz) }}"
    assert strategy["fail-fast"] is False
    assert strategy["max-parallel"] == 20
    assert set(re.findall(r"matrix\.(\w+)", str(job))) <= set(Piece.model_fields)


def test_pedaco_roda_so_pelo_lab_round_quando_executa(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["pedaco"]
    run = next(s for s in _steps(job) if s.get("name") == "Rodar o pedaço pelo lab_round")
    script = run["run"]

    assert script.count("tests.integration.lab_round") == 1
    assert "${{" not in script
    assert '--nivel "$NIVEL" --arquivo "$ARQUIVO"' in script
    assert '--trava "$RUNNER_TEMP/hdast-lab.lock"' in script
    assert "--sufixo=-gh${GITHUB_RUN_ID}a${GITHUB_RUN_ATTEMPT}p${INDICE}" in script
    assert 'args+=(--k "$MODO")' in script
    assert "HDAST_V17_DEADLINE_EPOCH=$(( $(date +%s) +" in script
    assert run["env"]["HDAST_IT_PREBUILT"] == "1"
    assert run["env"]["HDAST_IT_PREBUILT_TAG"] == "${{ needs.imagens.outputs.tag }}"
    assert run["timeout-minutes"] < job["timeout-minutes"]


def test_pedaco_publica_resultados_por_tres_dias_quando_termina(workflow: dict[str, Any]) -> None:
    steps = _steps(workflow["jobs"]["pedaco"])
    upload = next(s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact"))

    assert upload["with"]["name"] == "lab-${{ matrix.name }}"
    assert upload["with"]["retention-days"] == 3
    assert "!cancelled()" in upload["if"]
    assert any("proxy-watch.jsonl" in s.get("run", "") for s in steps)


def test_imagens_vao_pelo_cache_e_nunca_por_artefato_quando_compartilhadas(
    workflow: dict[str, Any],
) -> None:
    jobs = workflow["jobs"]
    builder = " ".join(str(step) for step in _steps(jobs["imagens"]))

    assert "tests.integration.lab_images" in builder
    assert "docker save" in builder
    assert "actions/cache/save" in builder
    assert not any(ref.startswith("actions/upload-artifact") for ref in _uses(jobs["imagens"]))
    assert "docker load" in " ".join(s.get("run", "") for s in _steps(jobs["pedaco"]))
    for token in ("docker/**", "lab/pilot/**", "scope_proxy/**", "compose.yaml", "pyproject.toml"):
        assert token in builder


def test_resumo_falha_com_o_pedaco_quando_roda_sempre(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["resumo"]
    commands = " ".join(step.get("run", "") for step in _steps(job))

    assert set(job["needs"]) == {"planejar", "pedaco"}
    assert "always()" in job["if"]
    assert ".github/scripts/lab_summary.py" in commands
    assert '--saida "$GITHUB_STEP_SUMMARY"' in commands
    download = next(s for s in _steps(job) if "download-artifact" in str(s.get("uses", "")))
    assert download["with"]["pattern"] == "lab-*"
