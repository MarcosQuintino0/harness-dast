"""Ensaio crapi-foco sem agente, executado pelo coordenador.

O arquivo reúne ciclo e evidências para preservar uma única preparação e um único down.
"""

import json
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from evals.runner.approve import approve
from evals.runner.cases import EvalError
from evals.runner.metrics import measure_agent
from evals.runner.prepare import prepare
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.run import is_run_id
from harness_dast.domain.scan_result import ScanResult
from harness_dast.domain.scope import OutboundRequest
from tests.integration.lab_proof_support import (
    execute,
    install_focus_spec,
    probe_attempts,
    summary,
)
from tests.integration.lab_resource_support import (
    ResourceGuard,
    docker_runner,
    inventory,
    verified_down,
)
from tests.integration.lab_support import REPO, CliResult, LabCli, require_docker
from tests.integration.run_support import record_metrics

pytestmark = pytest.mark.integration

EXPECTED = {
    "login",
    "check_otp_v2",
    "contact_mechanic",
    "validate_coupon",
    "get_vehicles",
    "get_location",
    "get_profile_video",
    "convert_profile_video",
    "update_profile_video",
    "get_products",
}
HEALTH_PATH = "/workshop/api/shop/products"


def _control_then_run(
    invoke: Callable[[str, tuple[str, ...], int], CliResult],
) -> tuple[CliResult, CliResult]:
    """Executa controle de leitura e uma única execução completa da carta."""
    probe = invoke("probe", ("probe", "crapi", "--only", "get_products"), 900)
    control = ProbeResult.model_validate(probe.data)
    assert probe.code == 0
    assert control.status == "completed"
    assert len(control.operations) == 1
    assert control.operations[0].operation_id == "get_products"
    assert control.operations[0].outcome == "success"
    assert control.operations[0].attempts > 0
    return probe, invoke("run", ("run", "crapi", "--max-minutes", "8"), 900)


def _configure_health_path(products: Path) -> None:
    """Ajusta somente o caminho de saúde livre do perfil descartável gerado pela carta."""
    profile = FileProfileRepository(products).load("crapi")
    profile.guard().ensure_allowed(
        OutboundRequest(method="GET", url=profile.environment.base_url + HEALTH_PATH)
    )
    target = products / "crapi" / "target.yml"
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    data.setdefault("probe", {})["health_path"] = HEALTH_PATH
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _remove_template_examples(products: Path) -> None:
    """Remove somente exemplos idênticos aos copiados pelo init no produto descartável."""
    product = products / "crapi"
    template = REPO / "products" / "_template"
    examples = [product / name for name in ("data-rules.yml", "flows.yml")]
    for example in examples:
        if example.is_symlink() or example.read_bytes() != (template / example.name).read_bytes():
            raise ValueError(f"Exemplo {example.name} foi alterado; revise antes do ensaio.")
    for example in examples:
        example.unlink()


def _run_evidence(runs: Path, run_id: str) -> dict[str, Any]:
    """Resume os artefatos validados sem copiar respostas, achados ou segredos."""
    if not is_run_id(run_id):
        raise ValueError("Identificador de execução inválido.")
    folder = runs / run_id
    run_probe = ProbeResult.model_validate_json((folder / "probe.json").read_text(encoding="utf-8"))
    probe_status, probe_attempt_counts = probe_attempts(run_probe.model_dump(mode="json"), EXPECTED)
    scan = ScanResult.model_validate_json((folder / "scan.json").read_text(encoding="utf-8"))
    authz = AuthzResult.model_validate_json((folder / "authz.json").read_text(encoding="utf-8"))
    negative = NegativeResult.model_validate_json(
        (folder / "negative.json").read_text(encoding="utf-8")
    )
    if any(
        item.run_id != run_id or item.product != "crapi" or item.dry_run
        for item in (run_probe, scan, authz, negative)
    ):
        raise ValueError("Artefato não pertence à execução real do ensaio.")
    return {
        "probe_status": probe_status,
        "probe_attempts": probe_attempt_counts,
        "scan_status": scan.status,
        "scan_planned": [item.operation_id for item in scan.planned],
        "scan_entries": [
            {
                "operation_id": entry.operation_id,
                "outcome": entry.outcome,
                "truncated": entry.truncated,
            }
            for entry in scan.entries
        ],
        "scan_skipped": [
            {"operation_id": item.operation_id, "reason": item.reason} for item in scan.skipped
        ],
        "scan_rule_gaps": [
            {"operation_id": item.operation_id, "state": item.state, "reason": item.reason}
            for item in scan.rule_coverage_gaps
        ]
        if scan.rule_coverage_gaps is not None
        else None,
        "authz_status": authz.status,
        "authz_checks": [
            {"check": item.check, "status": item.status, "tested": item.tested}
            for item in authz.checks
        ],
        "authz_not_tested": len(authz.not_tested),
        "authz_exclusions": [
            {"operation_id": item.operation_id, "check": item.check, "reason": item.reason}
            for item in authz.not_tested
            if item.operation_id in EXPECTED
        ],
        "negative_status": negative.status,
        "negative_operations_tested": negative.operations_tested,
        "negative_not_tested": len(negative.not_tested),
        "negative_exclusions": [
            {"operation_id": item.operation_id, "reason": item.reason}
            for item in negative.not_tested
            if item.operation_id in EXPECTED
        ],
    }


def _operational_complete(evidence: dict[str, Any]) -> bool:
    """Recusa interrupções ou varreduras individuais truncadas, sem prometer cobertura."""
    return (
        evidence["probe_status"] == "completed"
        and evidence["scan_status"] == "completed"
        and all(
            entry["outcome"] == "completed" and not entry["truncated"]
            for entry in evidence["scan_entries"]
        )
        and all(
            gap["state"] not in {"interrupted", "pending"}
            for gap in evidence["scan_rule_gaps"] or []
        )
        and evidence["authz_status"] == "completed"
        and all(check["status"] != "partial" for check in evidence["authz_checks"])
        and evidence["negative_status"] == "completed"
    )


def _has_complete_coverage(evidence: dict[str, Any]) -> bool:
    """Critério conservador: qualquer exclusão ou dado desconhecido impede afirmar cobertura."""
    scanned = {item["operation_id"] for item in evidence["scan_entries"]}
    planned_counts = Counter(evidence["scan_planned"])
    scanned_counts = Counter(item["operation_id"] for item in evidence["scan_entries"])
    return (
        _operational_complete(evidence)
        and set(evidence["probe_attempts"]) == EXPECTED
        and all(value > 0 for value in evidence["probe_attempts"].values())
        and bool(evidence["scan_planned"])
        and planned_counts <= scanned_counts
        and scanned >= EXPECTED
        and not evidence["scan_skipped"]
        and evidence["scan_rule_gaps"] == []
        and bool(evidence["authz_checks"])
        and all(
            check["status"] == "completed" and check["tested"] > 0
            for check in evidence["authz_checks"]
        )
        and evidence["authz_not_tested"] == 0
        and evidence["negative_operations_tested"] > 0
        and evidence["negative_not_tested"] == 0
    )


def _scan_limits(evidence: dict[str, Any]) -> list[str]:
    """Enumera lacunas do plano e das estatísticas do scan."""
    limits = []
    scanned = {item["operation_id"] for item in evidence["scan_entries"]}
    if not evidence["scan_planned"] or not scanned >= EXPECTED:
        limits.append("scan_nao_cobre_todas_operacoes")
    if not Counter(evidence["scan_planned"]) <= Counter(
        item["operation_id"] for item in evidence["scan_entries"]
    ):
        limits.append("scan_plano_sem_entradas_correspondentes")
    if evidence["scan_skipped"]:
        limits.append("scan_tem_exclusoes")
    if evidence["scan_rule_gaps"] is None:
        limits.append("scan_regras_indisponiveis")
    elif evidence["scan_rule_gaps"]:
        limits.append("scan_regras_com_lacunas")
    return limits


def _coverage_limits(evidence: dict[str, Any]) -> list[str]:
    """Enumera dados ausentes ou verificações sem cobertura completa."""
    limits = _scan_limits(evidence)
    if not _operational_complete(evidence):
        limits.append("execucao_operacional_incompleta")
    attempts = evidence["probe_attempts"]
    if set(attempts) != EXPECTED or any(attempts.get(name, 0) <= 0 for name in EXPECTED):
        limits.append("probe_tem_operacoes_nao_tentadas")
    if not evidence["authz_checks"] or any(
        item["status"] != "completed" or item["tested"] <= 0 for item in evidence["authz_checks"]
    ):
        limits.append("authz_checks_sem_cobertura_completa")
    if evidence["authz_not_tested"]:
        limits.append("authz_tem_exclusoes")
    if not evidence["negative_operations_tested"] or evidence["negative_not_tested"]:
        limits.append("negative_sem_cobertura_completa")
    return limits


def _transcript(out: Path, records: dict[str, Any]) -> None:
    """Representação de compatibilidade, gerada do ensaio, não conversa de agente."""
    events = []
    for index, (name, row) in enumerate(records.items()):
        if not isinstance(row, dict) or "started_at" not in row:
            continue
        command = {"up": "stack up", "down": "stack down"}.get(name, name)
        call = f"c{index}"
        events.extend(
            [
                {
                    "type": "assistant",
                    "timestamp": row["started_at"],
                    "message": {
                        "id": call,
                        "content": [
                            {
                                "type": "tool_use",
                                "id": call,
                                "name": "Bash",
                                "input": {"command": f"hdast {command} crapi"},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": row["finished_at"],
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": call,
                                "is_error": row["exit_code"] != 0,
                                "content": "resultado omitido",
                            }
                        ]
                    },
                },
            ]
        )
    (out / "transcript.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in events), encoding="utf-8"
    )


def test_crapi_foco_ensaio_sem_agente(tmp_path: Path) -> None:
    require_docker()
    started = time.monotonic()
    out = tmp_path / "ensaio"
    records: dict[str, Any] = {
        "proveniencia": "ensaio automatizado sem agente; transcript de compatibilidade",
        "meta_segundos": 900,
        "run_max_minutes": 8,
        "detectable": False,
        "cobertura_completa": False,
        "limites_cobertura": ["artefatos_indisponiveis"],
    }
    try:
        prepared = prepare("crapi-foco", "vulnerable", 0, out)
    except EvalError:
        records["prepare"] = {
            "status": "recusado",
            "detalhes": "verificar diagnostico do runner no terminal",
        }
        record_metrics("v112-crapi-foco-ensaio", records)
        raise
    records["prepare"] = {"exclusoes": list(prepared.excluded), "vazamentos": len(prepared.leaks)}
    cli = LabCli(tmp_path / "isolado", {})
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
    stack_attempted = False
    guard = ResourceGuard(lambda: inventory(docker_runner(cli.env)))
    flow_complete = False
    down_complete = False
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
        records["approval"] = "runner de ensaio"
        guard.before_up()
        stack_attempted = True
        up = execute(cli, records, "up", "stack", "up", "crapi", timeout=600)
        assert up.code == 0
        created = guard.capture()
        records["recursos_criados"] = {
            "containers": sorted(created.containers),
            "networks": sorted(created.networks),
            "volumes": sorted(created.volumes),
        }
        preflight = execute(cli, records, "preflight", "preflight", "crapi")
        assert preflight.code == 0
        assert preflight.data.get("ready") is True
        checks = {row["id"] for row in preflight.data.get("checks", []) if row.get("ok")}
        assert {"login:user_a", "login:user_b"} <= checks

        def invoke(name: str, args: tuple[str, ...], timeout: int) -> CliResult:
            return execute(cli, records, name, *args, timeout=timeout)

        _, run = _control_then_run(invoke)
        records["run_summary"] = summary(run)
        run_id = records["run_summary"]["run_id"]
        if run_id and (cli.runs / run_id / "probe.json").is_file():
            run_probe = ProbeResult.model_validate_json(
                (cli.runs / run_id / "probe.json").read_text(encoding="utf-8")
            )
            attempts = {
                operation.operation_id: operation.attempts
                for operation in run_probe.operations
                if operation.operation_id in EXPECTED
            }
            records["operacoes_run"] = attempts
            records["operacoes_outcomes_run"] = {
                operation.operation_id: operation.outcome
                for operation in run_probe.operations
                if operation.operation_id in EXPECTED
            }
            records["operacoes_nao_tentadas_run"] = sorted(
                operation for operation in EXPECTED if attempts.get(operation, 0) == 0
            )
        artifact_names = ("probe.json", "scan.json", "authz.json", "negative.json")
        missing = [
            name
            for name in artifact_names
            if not run_id or not (cli.runs / run_id / name).is_file()
        ]
        records["artefatos_ausentes"] = missing
        if not missing:
            evidence = _run_evidence(cli.runs, run_id)
            records["cobertura_run"] = evidence
            records["cobertura_completa"] = _has_complete_coverage(evidence)
            records["limites_cobertura"] = _coverage_limits(evidence)
        assert run.code in (0, 1)
        assert run_id
        assert records["run_summary"]["status"] in ("completed", "findings")
        assert not missing
        evidence = records["cobertura_run"]
        assert evidence["probe_status"] == "completed"
        assert set(evidence["probe_attempts"]) == EXPECTED
        assert all(value > 0 for value in evidence["probe_attempts"].values())
        assert evidence["scan_status"] == "completed"
        assert all(entry["outcome"] == "completed" for entry in evidence["scan_entries"])
        assert evidence["authz_status"] == "completed"
        assert all(check["status"] != "partial" for check in evidence["authz_checks"])
        assert evidence["negative_status"] == "completed"
        assert _operational_complete(evidence)
        stages = records["run_summary"]["stages"]
        assert [stage["name"] for stage in stages] == [
            "preflight",
            "probe",
            "scan",
            "authz",
            "negative",
            "report",
        ]
        assert all(stage["status"] == "ok" for stage in stages)
        flow_complete = True
    finally:
        try:
            if stack_attempted:
                verified_down(
                    guard,
                    lambda: execute(cli, records, "down", "stack", "down", timeout=240).code,
                    records,
                )
                down_complete = True
        finally:
            records["duracao_fim_a_fim_segundos"] = round(time.monotonic() - started, 3)
            records["conclusao_operacional_na_meta"] = (
                flow_complete and down_complete and records["duracao_fim_a_fim_segundos"] <= 900
            )
            if any(isinstance(v, dict) and "started_at" in v for v in records.values()):
                _transcript(out, records)
                metrics = measure_agent(out, "ensaio-sem-agente")
                # write_agent_metrics consulta segredos do lacre; não é permitido nesta tarefa.
                (out / "agent-metrics.json").write_text(
                    metrics.model_dump_json(indent=2) + "\n", encoding="utf-8"
                )
                records["medicao_runner"] = metrics.model_dump(mode="json")
                record_metrics("v112-crapi-foco-agent-metrics", metrics.model_dump(mode="json"))
            record_metrics("v112-crapi-foco-ensaio", records)
    assert records["duracao_fim_a_fim_segundos"] <= 900
