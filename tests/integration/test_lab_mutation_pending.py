"""Regressao crAPI para pendencias duraveis; execucao exclusiva pelo coordenador."""

import re
from pathlib import Path
from typing import Any

import pytest

from evals.runner.approve import approve
from evals.runner.prepare import prepare
from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.domain.probe_result import ProbeResult
from tests.integration.lab_support import LabCli, proxy_audit, require_docker, run_audit
from tests.integration.run_support import record_metrics
from tests.integration.test_crapi_focus_dryrun import (
    _configure_health_path,
    _remove_template_examples,
)
from tests.integration.v112_proof_support import execute, install_focus_spec, read_scan, summary
from tests.integration.v112_resource_support import (
    ResourceGuard,
    docker_runner,
    inventory,
    verified_down,
)

pytestmark = pytest.mark.integration
BLOCKED = {"check_otp_v2", "validate_coupon"}


def test_lab_mutation_pending_nao_reenvia_e_varre_demais(tmp_path: Path) -> None:
    require_docker()
    out = tmp_path / "ensaio"
    prepared = prepare("crapi-foco", "vulnerable", 0, out)
    cli = LabCli(tmp_path / "isolado", {})
    cli.env["HDAST_STACK_PROJECT_SUFFIX"] = "-codex"
    cli.products = prepared.workspace / "products"
    cli.runs = prepared.workspace / "runs"
    cli.state = out / "state"
    cli.runs.mkdir(exist_ok=True)
    cli.env.update(
        {
            "HDAST_PRODUCTS_DIR": str(cli.products),
            "HDAST_RUNS_DIR": str(cli.runs),
            "HDAST_STATE_DIR": str(cli.state),
        }
    )
    for key in tuple(cli.env):
        if key.startswith("CRAPI_"):
            del cli.env[key]
    records: dict[str, Any] = {}
    guard = ResourceGuard(lambda: inventory(docker_runner(cli.env)))
    stack_attempted = False
    try:
        init = execute(
            cli,
            records,
            "init",
            "init",
            "crapi",
            "--from-letter",
            str(prepared.workspace / "inputs/carta.yml"),
        )
        assert init.code == 0
        install_focus_spec(prepared.workspace, cli.products)
        _remove_template_examples(cli.products)
        _configure_health_path(cli.products)
        approve(out)
        guard.before_up()
        stack_attempted = True
        assert execute(cli, records, "up", "stack", "up", "crapi", timeout=600).code == 0
        guard.capture()
        assert execute(cli, records, "preflight", "preflight", "crapi").data.get("ready") is True
        first = execute(cli, records, "probe", "probe", "crapi", timeout=900)
        assert first.code == 0
        first_probe = ProbeResult.model_validate(first.data)
        failures = {
            op.operation_id: op for op in first_probe.operations if op.operation_id in BLOCKED
        }
        assert set(failures) == BLOCKED
        assert all(op.outcome == "server_error" and op.status == 500 for op in failures.values())
        records["first_probe_id"] = first_probe.run_id
        first_audit = run_audit(cli, first_probe.run_id)
        assert {
            row["operation_id"]
            for row in first_audit
            if row["phase"] == "result" and row["status"] == 500
        } >= BLOCKED
        assert all(op.attempts == 1 for op in failures.values())
        pending = FileMutationJournal(cli.state / "mutations").list_pending()
        pending_context = {
            item.metadata.operation_id: item.metadata for item in pending if item.metadata
        }
        assert pending_context.keys() >= BLOCKED
        assert all(pending_context[op].run_id == first_probe.run_id for op in BLOCKED)
        assert all(pending_context[op].account == failures[op].account for op in BLOCKED)
        before_proxy = proxy_audit(cli)
        blocked_paths = {op.path for op in failures.values()}
        for path in blocked_paths:
            assert (
                len(
                    [
                        row
                        for row in before_proxy
                        if row["method"] == "POST"
                        and row["path"] == path
                        and row["decision"] == "allow"
                    ]
                )
                == 1
            )
        run = execute(cli, records, "run", "run", "crapi", "--max-minutes", "8", timeout=900)
        records["run_summary"] = summary(run)
        run_summary = records["run_summary"]
        raw_error = records["run"].get("error_code")
        error_code = (
            raw_error
            if isinstance(raw_error, str) and re.fullmatch(r"[A-Z0-9_]{1,64}", raw_error)
            else None
        )
        sanitized_summary = {
            "run_id": run_summary["run_id"],
            "status": run_summary["status"]
            if run_summary["status"] in {"completed", "findings", "failed", "interrupted"}
            else None,
            "stages": [
                {"name": row["name"], "status": row["status"]}
                for row in run_summary["stages"]
                if row["name"] in {"preflight", "probe", "scan", "authz", "negative", "report"}
                and row["status"] in {"ok", "skipped", "failed", "interrupted"}
            ],
        }
        diagnostic = f"codigo={run.code}, error_code={error_code}, resumo={sanitized_summary}"
        assert run.code in (0, 1), diagnostic
        run_id = run_summary["run_id"]
        assert run_id, diagnostic
        stages = {row["name"]: row["status"] for row in summary(run)["stages"]}
        assert all(stages[name] == "ok" for name in ("scan", "authz", "negative", "report"))
        after_proxy = proxy_audit(cli)
        assert not [
            row
            for row in after_proxy[len(before_proxy) :]
            if row["method"] == "POST"
            and row["path"] in blocked_paths
            and row["decision"] == "allow"
        ]
        second = ProbeResult.model_validate_json(
            (cli.runs / run_id / "probe.json").read_text(encoding="utf-8")
        )
        skipped = {op.operation_id: op for op in second.operations if op.operation_id in BLOCKED}
        assert set(skipped) == BLOCKED
        assert all(op.outcome == "mutation_pending" and op.attempts == 0 for op in skipped.values())
        assert any(
            op.outcome == "success" for op in second.operations if op.operation_id not in BLOCKED
        )
        run_rows = run_audit(cli, run_id)
        assert {
            row["operation_id"]
            for row in run_rows
            if row["phase"] == "decision"
            and row["decision"] == "denied"
            and row["reason"] == "mutation_pending"
        } >= BLOCKED
        assert not [
            row
            for row in run_rows
            if row["operation_id"] in BLOCKED
            and row["method"] == "POST"
            and (row["phase"] == "result" or row["decision"] == "allowed")
        ]
        assert "mutation_pending" in (cli.runs / run_id / "report.html").read_text(encoding="utf-8")
        assert execute(cli, records, "panel", "panel", "crapi", "--run", run_id).code == 0
        pages = (cli.runs / run_id / "panel").glob("*.html")
        assert any("mutation_pending" in page.read_text(encoding="utf-8") for page in pages)
        scan = read_scan(cli.runs, run_id)
        assert any(
            entry.operation_id not in BLOCKED and entry.outcome == "completed"
            for entry in scan.entries
        )
        assert not [
            entry
            for entry in scan.entries
            if entry.operation_id in BLOCKED and entry.outcome == "completed"
        ]
    finally:
        try:
            if stack_attempted:
                verified_down(
                    guard,
                    lambda: execute(cli, records, "down", "stack", "down", timeout=240).code,
                    records,
                )
        finally:
            record_metrics("v1121-mutation-pending", records)
