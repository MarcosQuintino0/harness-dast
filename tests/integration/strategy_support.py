"""Apoio da prova V1.8: ativação explícita e observações sem respostas ou credenciais."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from tests.integration.lab_support import (
    PILOT_PROFILE,
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    LabCli,
)
from tests.integration.run_support import record_metrics


def install_strategy(cli: LabCli, product: str) -> Path:
    """Instala a cópia do laboratório e ativa só a estratégia gerada explicitamente."""
    source = PILOT_PROFILE if product == "clinica-piloto" else VAMPI_PROFILE
    extras = () if product == "clinica-piloto" else (VAMPI_OPENAPI,)
    folder = cli.install_product(product, source, extras)
    activate_strategy(cli, product)
    return folder


def activate_strategy(cli: LabCli, product: str) -> None:
    """Migra sem alterar o perfil; o teste decide ativar o arquivo neutro produzido."""
    folder = cli.products / product
    before = (folder / "target.yml").read_bytes()
    result = cli.run("strategy", "migrate", product)
    assert result.code == 0, result.stdout + result.stderr
    assert (folder / "target.yml").read_bytes() == before
    assert not (folder / "strategy.yml").exists()
    (folder / "strategy.migrated.yml").rename(folder / "strategy.yml")
    valid = cli.run("strategy", "validate", product)
    assert valid.code == 0, valid.stdout + valid.stderr
    planned = cli.run("plan", product, "--dry-run")
    assert planned.code == 0, planned.stdout + planned.stderr


def load_artifact(cli: LabCli, run_id: str, name: str) -> dict[str, Any]:
    """Lê somente um artefato redigido que o teste precisa conferir."""
    loaded = json.loads((cli.runs / run_id / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def bind_live_strategy(cli: LabCli, product: str) -> None:
    """Cria o vínculo pelo comando público e ativa explicitamente a cópia no laboratório."""
    folder = cli.products / product
    before = (folder / "target.yml").read_bytes()
    active = folder / "strategy.yml"
    strategy_before = active.read_bytes()
    captured = cli.run("strategy", "capture", product)
    assert captured.code == 0, captured.stdout + captured.stderr
    assert captured.data["copy"] == "strategy.captured.yml"
    assert captured.data["activated"] is False
    assert captured.data["approval_changed"] is False
    assert (folder / "target.yml").read_bytes() == before
    assert active.read_bytes() == strategy_before
    active.rename(folder / "strategy.unbound.yml")
    (folder / "strategy.captured.yml").rename(active)


def record_control(product: str, mode: str, artifacts: dict[str, dict[str, Any]]) -> None:
    """Registra cobertura, técnicas e lacunas sem valores enviados ou respostas."""
    payload: dict[str, Any] = {
        "product": product,
        "mode": mode,
        "run_id": artifacts["scan"]["run_id"],
    }
    for stage, data in artifacts.items():
        assert data["run_id"] == payload["run_id"]
        payload[stage] = {
            "status": data["status"],
            "requests_sent": data.get("requests_sent"),
            "checks": data.get("checks"),
            "by_class": data.get("by_class"),
            "by_operation": data.get("by_operation"),
            "entries": data.get("entries"),
            "planned": data.get("planned"),
            "skipped": data.get("skipped"),
            "policy": data.get("policy"),
            "limits": data.get("limits"),
            "traffic": data.get("traffic"),
            "findings_by_technique": dict(
                Counter(item["technique"] for item in data.get("findings", []))
            ),
            "not_tested_reasons": dict(
                Counter(item["reason"] for item in data.get("not_tested", []))
            ),
        }
    record_metrics(f"v18-t2-{product}-{mode}", payload)


def legacy_anonymous_findings(cli: LabCli, product: str, run_id: str) -> list[dict[str, Any]]:
    """Compara apenas leituras anônimas, preservando separados os dois artefatos reais."""
    product_dir = cli.products / product
    strategy = product_dir / "strategy.yml"
    paused = product_dir / "strategy.paused.yml"
    run_dir = cli.runs / run_id
    current = run_dir / "authz.json"
    saved = run_dir / "authz-strategy.json"
    current.rename(saved)
    strategy.rename(paused)
    try:
        result = cli.run("authz", product, "--run", run_id, "--check", "anonymous_access")
        assert result.code == 0, result.stdout + result.stderr
        return list(load_artifact(cli, run_id, "authz.json")["findings"])
    finally:
        if current.exists():
            current.rename(run_dir / "authz-legacy-anonymous.json")
        saved.rename(current)
        paused.rename(strategy)


def finding_keys(findings: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """Retorna técnica, operação e severidade sem resposta, conta ou identificador efêmero."""
    return sorted(
        (item["technique"], item["operation_id"], item["proposed_severity"]) for item in findings
    )
