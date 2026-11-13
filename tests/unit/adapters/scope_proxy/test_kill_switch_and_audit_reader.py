"""`FileKillSwitch` e `FileProxyAudit`: leitura de arquivos reais em pasta temporária."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.scope_proxy.audit_reader import FileProxyAudit
from harness_dast.adapters.scope_proxy.kill_switch import FileKillSwitch
from harness_dast.domain.errors import ConfigError


def test_kill_switch_is_engaged_only_when_the_kill_file_exists(tmp_path: Path) -> None:
    switch = FileKillSwitch(tmp_path)
    assert switch.engaged() is False

    (tmp_path / "KILL").touch()

    assert switch.engaged() is True


def test_kill_switch_without_a_known_policy_dir_is_never_engaged() -> None:
    assert FileKillSwitch(None).engaged() is False


def _line(**changes: object) -> str:
    base = {
        "ts": "2026-11-13T10:00:00.000+00:00",
        "method": "GET",
        "decision": "allow",
        "reason": "allowed",
        "path": "/x",
    }
    return json.dumps({**base, **changes})


def test_audit_reader_parses_rows_and_ignores_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text(_line() + "\n\n" + _line(decision="deny", reason="path_not_allowed") + "\n")

    rows = FileProxyAudit(path).rows()

    assert [r.decision for r in rows] == ["allow", "deny"]


def test_audit_reader_returns_nothing_when_the_file_does_not_exist(tmp_path: Path) -> None:
    assert FileProxyAudit(tmp_path / "nao-existe.jsonl").rows() == ()


@pytest.mark.parametrize("content", ["isto não é json", '{"ts": "ontem"}', "[1, 2]"])
def test_audit_reader_raises_config_error_on_malformed_lines(tmp_path: Path, content: str) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text(content + "\n")

    with pytest.raises(ConfigError, match="ilegível"):
        FileProxyAudit(path).rows()
