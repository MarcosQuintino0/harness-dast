"""Prova de revogacao em voo pelo proxy real, apenas no VAmPI de laboratorio."""

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import VAMPI_OPENAPI, VAMPI_PROFILE, LabCli, require_docker
from tests.integration.run_support import record_metrics
from tests.integration.test_lab_vampi import SEEDED

pytestmark = pytest.mark.integration
_WAIT_SECONDS = 120.0
_PROCESS_TIMEOUT = 180
_POLL_SECONDS = 0.1
_MAX_AUDIT_BYTES = 2 * 1024 * 1024


def _install(cli: LabCli) -> None:
    folder = cli.install_product("vampi", VAMPI_PROFILE, (VAMPI_OPENAPI,))
    path = folder / "target.yml"
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    profile["limits"]["requests_per_second"] = 1
    profile.setdefault("scan", {})["pacing"] = "proxy"
    path.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")


def _audit(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_AUDIT_BYTES + 1)
    except FileNotFoundError:
        return []
    assert len(raw) <= _MAX_AUDIT_BYTES, "auditoria excedeu limite de leitura"
    # A ultima linha pode estar sendo escrita pelo proxy; esperar ate ficar completa.
    lines = raw.split(b"\n")[:-1]
    rows = [json.loads(line) for line in lines if line]
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _wait_for(
    path: Path, process: subprocess.Popen[str], start: int, *, decision: str, reason: str | None
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + _WAIT_SECONDS
    while time.monotonic() < deadline:
        rows = _audit(path)[start:]
        if any(
            row.get("decision") == decision and (reason is None or row.get("reason") == reason)
            for row in rows
        ):
            return rows
        assert process.poll() is None, f"probe terminou antes da decisao {decision}/{reason}"
        time.sleep(_POLL_SECONDS)
    pytest.fail(f"tempo esgotado esperando decisao {decision}/{reason}")


def test_revogacao_durante_probe_trava_concessoes_no_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compila, inicia o probe, revoga o arquivo temporario e observa a recusa real."""
    require_docker()
    cli = LabCli(tmp_path, SEEDED)
    _install(cli)
    process: subprocess.Popen[str] | None = None
    audit_path: Path | None = None
    start = 0
    started = time.monotonic()
    revoked_at: float | None = None
    denied_at: float | None = None
    run_id = ""
    exit_code: int | None = None
    try:
        up = cli.run("stack", "up", "vampi", "--build", timeout=900)
        assert up.code == 0, "nao foi possivel subir a pilha de laboratorio"
        audit_name = up.data.get("audit_file")
        assert isinstance(audit_name, str)
        audit_path = Path(audit_name)
        run_id = str(up.data.get("run_id", ""))
        assert run_id
        start = len(_audit(audit_path))
        process = cli.start("probe", "vampi")
        # A revogacao nao pode ser recriada por stack_down ou por outra chamada do helper.
        monkeypatch.setattr(cli, "approve_installed_products", lambda: None)
        _wait_for(audit_path, process, start, decision="allow", reason=None)
        approval = cli.state / "approvals" / "vampi.json"
        assert approval.resolve().is_relative_to(tmp_path.resolve())
        assert approval.is_file()
        approval.unlink()
        revoked_at = time.monotonic()
        _wait_for(audit_path, process, start, decision="deny", reason="approval_changed")
        denied_at = time.monotonic()
        process.communicate(timeout=_PROCESS_TIMEOUT)
        exit_code = process.returncode
        rows = _audit(audit_path)[start:]
        first_deny = next(
            index
            for index, row in enumerate(rows)
            if row.get("decision") == "deny" and row.get("reason") == "approval_changed"
        )
        assert any(row.get("decision") == "allow" for row in rows[:first_deny])
        assert not any(row.get("decision") == "allow" for row in rows[first_deny + 1 :])
    finally:
        try:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=15)
                exit_code = process.returncode
            _save_evidence(audit_path, start, started, revoked_at, denied_at, run_id, exit_code)
        finally:
            cli.stack_down()


def _save_evidence(
    audit_path: Path | None,
    start: int,
    started: float,
    revoked_at: float | None,
    denied_at: float | None,
    run_id: str,
    exit_code: int | None,
) -> None:
    rows = _audit(audit_path)[start:] if audit_path is not None else []
    record_metrics(
        "v18-revocation-vampi",
        {
            "run_id": run_id,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "revoked_after_seconds": None if revoked_at is None else round(revoked_at - started, 3),
            "denial_after_seconds": None
            if denied_at is None or revoked_at is None
            else round(denied_at - revoked_at, 3),
            "process_exit_code": exit_code,
            "decisions": [
                {"decision": row.get("decision"), "reason": row.get("reason")} for row in rows
            ],
        },
    )
