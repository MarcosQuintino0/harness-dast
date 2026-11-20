"""Contrato do `scan` com `scan.include_outcomes` (ADR 0050): a flag só escolhe dentro do perfil."""

from pathlib import Path

import pytest

from harness_dast.domain.errors import ExitCode
from tests.contract.test_cli_probe_commands import (
    _env,  # noqa: F401 - fixture autouse do módulo do probe
    environment,
    invoke_json,
)
from tests.contract.test_cli_scan_report import Combined, probe_then, scan_args

pytestmark = pytest.mark.contract


def test_a_flag_outside_the_profile_list_exits_2_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        before = (len(server.requests), len(combined.scan.calls))
        code, envelope, _ = invoke_json(
            capsys, *scan_args(run_id, products, "--include-outcome", "not_found", "--dry-run")
        )
        after = (len(server.requests), len(combined.scan.calls))

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert "não lista" in envelope["error"]["message"]
    assert before == after


def test_a_flag_inside_the_profile_list_exits_0_and_reports_the_applied_classes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(
        monkeypatch, tmp_path, combined, scan={"include_outcomes": ["not_found", "conflict"]}
    ) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        code, envelope, _ = invoke_json(
            capsys, *scan_args(run_id, products, "--include-outcome", "not_found", "--dry-run")
        )
        plain_code, plain, _ = invoke_json(capsys, *scan_args(run_id, products, "--dry-run"))

    assert code == ExitCode.OK
    assert envelope["data"]["include_outcomes"] == ["not_found"]
    assert plain_code == ExitCode.OK
    assert plain["data"]["include_outcomes"] == ["not_found", "conflict"]


def test_no_include_outcomes_reduces_the_list_to_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined, scan={"include_outcomes": ["not_found"]}) as (
        server,
        products,
    ):
        run_id = probe_then(capsys, products, server, combined)
        code, envelope, _ = invoke_json(
            capsys, *scan_args(run_id, products, "--no-include-outcomes", "--dry-run")
        )

    assert code == ExitCode.OK
    assert envelope["data"]["include_outcomes"] == []


def test_the_two_flags_together_are_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined, scan={"include_outcomes": ["not_found"]}) as (
        server,
        products,
    ):
        run_id = probe_then(capsys, products, server, combined)
        code, _, _ = invoke_json(
            capsys,
            *scan_args(run_id, products, "--include-outcome", "not_found", "--no-include-outcomes"),
        )

    assert code == ExitCode.USAGE
