"""Contrato de `hdast retestar`: envelope JSON, códigos de saída, erros de uso e o aviso.

O caso de uso é testado em `tests/unit/application/test_retest.py`; aqui a montagem da CLI é
trocada por um caso de uso falso para provar só o contrato: `data` traz `retest` e `run`, o
código de saída é o do reteste, e o texto nunca diz que o achado foi corrigido.
"""

import json
from dataclasses import dataclass
from typing import Any

import pytest

from harness_dast.application.retest import RetestOutcome, RetestRequest
from harness_dast.application.run import RunResult
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import retestar as retestar_command
from harness_dast.domain.errors import ConfigError, ExitCode, HarnessError, ScopeViolation
from harness_dast.domain.finding_diff import COMPARISON_NOTICE
from harness_dast.domain.retest import RetestReport, build_retest_report
from harness_dast.domain.run_summary import RunOptions, RunSummary, StageRecord
from tests.fakes.verification_data import finding

pytestmark = pytest.mark.contract

RUN_ID = "2026-11-13T10-00-00Z-demo-aaaa"
BEFORE = "2026-11-12T10-00-00Z-demo-0001"
SEEN: list[RetestRequest] = []


def _summary(code: int) -> RunSummary:
    names = ("preflight", "probe", "scan", "authz", "negative", "report")
    return RunSummary(
        product="demo",
        run_id=RUN_ID,
        status="completed" if code == 0 else "failed",
        exit_code=code,
        started_at="2026-11-13T10:00:00+00:00",
        finished_at="2026-11-13T10:01:00+00:00",
        duration_seconds=60.0,
        options=RunOptions(),
        stages=tuple(StageRecord(name=n, status="ok") for n in names),  # type: ignore[arg-type]  # nomes literais
        artifacts={"findings.json": "findings.json"},
    )


def _report(*, reproduced: bool) -> RetestReport:
    item = finding().model_copy(update={"operation_id": "getPet"})
    return build_retest_report(
        product="demo",
        previous_run_id=BEFORE,
        run_id=RUN_ID,
        generated_at="2026-11-13T10:01:00+00:00",
        selected=[item],
        current=[item] if reproduced else [],
        scanned_operations={"getPet"},
    )


@dataclass
class _UseCase:
    outcome: RetestOutcome

    def execute(self, request: RetestRequest) -> RetestOutcome:
        SEEN.append(request)
        return self.outcome


class _Net:
    def close(self) -> None:
        return None


def _install(monkeypatch: pytest.MonkeyPatch, outcome: RetestOutcome) -> None:
    SEEN.clear()
    monkeypatch.setattr(retestar_command, "open_scan_network", lambda *a, **k: _Net())
    monkeypatch.setattr(retestar_command, "build_retest", lambda *a, **k: _UseCase(outcome))


def _outcome(
    *, code: int = 0, reproduced: bool = False, error: HarnessError | None = None
) -> RetestOutcome:
    report = None if error is not None else _report(reproduced=reproduced)
    return RetestOutcome(RunResult(_summary(code), error), report, code, error)


def _call(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any]]:
    code = run_app(build_app(), [*args])
    return code, json.loads(capsys.readouterr().out)


def test_retest_envelope_carries_the_report_the_run_and_the_notice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _install(monkeypatch, _outcome())

    code, envelope = _call(capsys, "--json", "retestar", "demo", "--run", BEFORE)

    assert code == int(ExitCode.OK)
    assert envelope["ok"] is True
    assert envelope["run_id"] == RUN_ID
    assert set(envelope["data"]) == {"retest", "run"}
    assert envelope["data"]["retest"]["notice"] == COMPARISON_NOTICE
    assert envelope["data"]["retest"]["entries"][0]["result"] == "not_reproduced"
    assert envelope["data"]["retest"]["schema_version"] == 1
    assert envelope["data"]["run"]["run_id"] == RUN_ID


def test_retest_exits_with_findings_code_when_a_finding_is_reproduced(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _install(monkeypatch, _outcome(code=1, reproduced=True))

    code, envelope = _call(capsys, "--json", "retestar", "demo", "--run", BEFORE)

    assert code == int(ExitCode.FINDINGS)
    assert envelope["ok"] is True
    assert envelope["data"]["retest"]["counts"]["reproduced"] == 1


def test_retest_failure_keeps_the_run_error_and_the_run_data(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    error = ScopeViolation("janela fechada", hint="Espere a janela.")
    _install(monkeypatch, _outcome(code=3, error=error))

    code, envelope = _call(capsys, "--json", "retestar", "demo", "--run", BEFORE)

    assert code == int(ExitCode.SCOPE)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == error.code
    assert envelope["data"]["retest"] is None


def test_retest_passes_the_options_to_the_use_case(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _install(monkeypatch, _outcome())

    _call(
        capsys,
        "--json",
        "retestar",
        "demo",
        "--run",
        BEFORE,
        "--finding",
        "a" * 64,
        "--finding",
        "b" * 64,
        "--max",
        "3",
        "--fail-on",
        "high",
        "--max-minutes",
        "5",
    )

    assert len(SEEN) == 1
    assert SEEN[0] == RetestRequest(
        product="demo",
        previous_run_id=BEFORE,
        findings=("a" * 64, "b" * 64),
        max_findings=3,
        fail_on="high",
        max_minutes=5,
    )


def test_retest_defaults_to_ten_findings_and_no_explicit_choice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _install(monkeypatch, _outcome())

    _call(capsys, "--json", "retestar", "demo", "--run", BEFORE)

    assert (SEEN[0].findings, SEEN[0].max_findings, SEEN[0].fail_on) == ((), 10, None)


@pytest.mark.parametrize("value", ["0", "31", "-1", "abc"])
def test_retest_rejects_max_out_of_range_as_usage_error(
    capsys: pytest.CaptureFixture[str], value: str
) -> None:
    code, envelope = _call(capsys, "--json", "retestar", "demo", "--run", BEFORE, "--max", value)

    assert code == int(ExitCode.USAGE)
    assert envelope["ok"] is False


def test_retest_requires_the_previous_run(capsys: pytest.CaptureFixture[str]) -> None:
    code, envelope = _call(capsys, "--json", "retestar", "demo")

    assert code == int(ExitCode.USAGE)
    assert envelope["error"]["code"] == "CONFIG_ERROR"


def test_retest_use_case_error_becomes_a_usage_envelope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _Failing:
        def execute(self, request: RetestRequest) -> RetestOutcome:
            raise ConfigError("A execução não tem findings.json.", hint="Confira o run_id.")

    monkeypatch.setattr(retestar_command, "open_scan_network", lambda *a, **k: _Net())
    monkeypatch.setattr(retestar_command, "build_retest", lambda *a, **k: _Failing())

    code, envelope = _call(capsys, "--json", "retestar", "demo", "--run", BEFORE)

    assert code == int(ExitCode.USAGE)
    assert envelope["error"]["hint"] == "Confira o run_id."


def test_retest_human_output_never_says_fixed_and_shows_the_notice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _install(monkeypatch, _outcome())

    run_app(build_app(), ["retestar", "demo", "--run", BEFORE])
    text = capsys.readouterr().out

    assert "não reproduzido nesta execução" in text
    assert COMPARISON_NOTICE in text
    assert "foi corrigido" not in text.replace("não prova", "")
