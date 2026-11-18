"""Confere o contrato do laboratório no GitHub sem iniciar contêineres."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/lab.yml"
pytestmark = pytest.mark.contract


@pytest.fixture
def workflow() -> dict[str, Any]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_workflow_restringe_disparos_quando_em_pull_request(workflow: dict[str, Any]) -> None:
    events = workflow["on"]

    assert set(events) == {"workflow_dispatch", "pull_request"}
    assert set(events["pull_request"]["types"]) == {"labeled", "synchronize"}
    assert events["workflow_dispatch"]["inputs"]["nivel"]["options"] == ["carga"]
    for job in workflow["jobs"].values():
        assert "contains(github.event.pull_request.labels.*.name, 'lab')" in job["if"]


def test_workflow_respeita_leitura_e_prazo_quando_executa(workflow: dict[str, Any]) -> None:
    assert workflow["permissions"] == {"contents": "read"}
    for job in workflow["jobs"].values():
        assert all(value == "read" for value in job.get("permissions", {}).values())
        assert not re.search(r"\bsecrets\s*[.\[]", str(job), re.IGNORECASE)
        assert isinstance(job["timeout-minutes"], int)
        assert job["timeout-minutes"] > 0


def test_lab_round_executa_so_o_benchmark_quando_disparado(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["cerca"]
    commands = [step.get("run", "") for step in job["steps"]]
    rounds = [command for command in commands if "tests.integration.lab_round" in command]

    assert len(rounds) == 1
    assert re.findall(r"--arquivo (\S+)", rounds[0]) == ["test_guard_benchmark.py"]
    assert '--sufixo="-gh' in rounds[0]
    assert "${{" not in rounds[0]
    assert job["concurrency"] == {
        "group": "lab-${{ github.ref }}",
        "cancel-in-progress": True,
    }


@pytest.mark.parametrize(
    ("cases", "expected_counts", "expected_exit"),
    [
        ('<testcase name="cerca" time="0.5"/>', "1 aprovados · 0 falharam · 0 pulados", 0),
        (
            '<testcase name="rápido" time="0.5"/><testcase name="lento" time="2.5"><error/>'
            '</testcase><testcase name="pulou"><skipped/></testcase>',
            "1 aprovados · 1 falharam · 1 pulados",
            1,
        ),
        ('<testcase name="pulou"><skipped/></testcase>', "0 aprovados · 0 falharam · 1 pulados", 1),
        ("", "0 aprovados · 0 falharam · 0 pulados", 1),
    ],
)
def test_resumo_reflete_o_junit_quando_coletado(
    workflow: dict[str, Any], tmp_path: Path, cases: str, expected_counts: str, expected_exit: int
) -> None:
    steps = workflow["jobs"]["cerca"]["steps"]
    script = next(step["run"] for step in steps if step.get("name") == "Resumir a rodada")
    output = tmp_path / "output"
    output.mkdir()
    if cases:
        (output / "junit.xml").write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")
    pytest_output = tmp_path / "pytest"
    test_directory = pytest_output / "test_cerca0"
    test_directory.mkdir(parents=True)
    watch = {"stack_run_id": "stack-1", "categories": ["profile_changed"], "status": "ok"}
    (test_directory / "proxy-watch.jsonl").write_text(json.dumps(watch) + "\n", encoding="utf-8")
    summary = tmp_path / "summary.md"

    result = subprocess.run(  # noqa: S603 - roda apenas o relatório com arquivos sintéticos.
        (sys.executable, "-c", "\n".join(script.splitlines()[1:-1])),
        env=dict(
            os.environ,
            LAB_OUTPUT=str(output),
            LAB_PYTEST=str(pytest_output),
            GITHUB_STEP_SUMMARY=str(summary),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == expected_exit, result.stderr
    report = summary.read_text(encoding="utf-8")
    assert expected_counts in report
    assert "Pilha <code>stack-1</code> · <code>profile_changed</code>" in report
    if "lento" in cases:
        assert report.index("2.50 s") < report.index("0.50 s")
