"""Contrato de `stack pull` com o registro e o Docker em memória."""

import json
from pathlib import Path

import pytest

from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import stack
from harness_dast.cli.stack_lock_composition import hold_stack
from harness_dast.domain.errors import ExitCode
from tests.fakes.host import FakeHost

pytestmark = pytest.mark.contract


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeHost:
    fake = FakeHost()
    fake.present.clear()
    monkeypatch.setattr(stack, "build_stack_images", fake.stack_images)
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path))
    return fake


def test_pull_returns_the_two_image_references_in_the_success_envelope(
    host: FakeHost, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_app(build_app(), ["stack", "pull", "--json"])

    assert code == ExitCode.OK
    own = [host.images["zap"], host.images["scope-proxy"]]
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": 1,
        "ok": True,
        "data": {"images": own},
    }
    assert host.present == set(own)


@pytest.mark.parametrize(
    ("failure", "exit_code", "error_code"),
    [
        ("missing_service", ExitCode.USAGE, "CONFIG_ERROR"),
        ("pull", ExitCode.EXTERNAL_TOOL, "EXTERNAL_TOOL_ERROR"),
    ],
)
def test_pull_returns_the_failure_envelope_with_a_hint(
    host: FakeHost,
    capsys: pytest.CaptureFixture[str],
    failure: str,
    exit_code: int,
    error_code: str,
) -> None:
    if failure == "missing_service":
        del host.images["scope-proxy"]
    else:
        host.remote.remove(host.images["scope-proxy"])

    code = run_app(build_app(), ["--json", "stack", "pull"])

    assert code == exit_code
    envelope = json.loads(capsys.readouterr().out)
    assert set(envelope) == {"schema_version", "ok", "error"}
    assert envelope["schema_version"] == 1
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == error_code
    assert envelope["error"]["hint"]


def test_pull_respects_the_stack_lock(host: FakeHost, capsys: pytest.CaptureFixture[str]) -> None:
    with hold_stack("stack up", "demo"):
        code = run_app(build_app(), ["--json", "stack", "pull"])

    assert code == ExitCode.BUSY
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "STACK_BUSY"
    assert not host.present
