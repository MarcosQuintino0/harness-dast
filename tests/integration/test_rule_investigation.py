"""Passo zero V1.9: duas regras isoladas, sem repetir a varredura completa."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import proxy_audit, require_docker
from tests.integration.rule_diagnostics_support import (
    baseline_rules,
    source_hashes,
    summarize_messages,
)
from tests.integration.run_support import ZapHistory, record_metrics
from tests.integration.test_lab_strategy import _cli
from tests.integration.test_scan_performance_matrix import _install

pytestmark = [pytest.mark.integration, pytest.mark.lab_prova]


@pytest.mark.parametrize(
    ("product", "operation", "rule"),
    [
        ("clinica-piloto", "atualizarPaciente", 90035),
        ("vampi", "api_views.books.get_by_title", 40008),
    ],
)
@pytest.mark.parametrize("variant", ["A", "B"])
def test_v19_investiga_regra_dirigida(
    tmp_path: Path, product: str, operation: str, rule: int, variant: str
) -> None:
    """Uma pilha nova por célula; todos os resultados são preservados, inclusive falhas.

    O ciclo permanece junto para coletar somente metadados antes da desmontagem.
    A política reduzida diagnostica a regra e não substitui T4 nem prova equivalência histórica.
    """
    require_docker()
    cli = _cli(tmp_path, product)
    _install(cli, product, variant)
    path = cli.products / product / "target.yml"
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    profile.setdefault("scan", {})["disable_rules"] = [
        ident for ident in baseline_rules() if ident != rule
    ]
    path.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")
    record: dict[str, Any] = {
        "product": product,
        "operation": operation,
        "rule": rule,
        "variant": variant,
        "sources": source_hashes(),
    }
    try:
        up = cli.run("stack", "up", product, "--build", timeout=900)
        record["up_exit"] = up.code
        assert up.code == 0, up.stdout + up.stderr
        assert cli.run("preflight", product, timeout=420).code == 0
        probe = cli.run("probe", product, timeout=900)
        record["probe_exit"] = probe.code
        assert probe.code == 0, probe.stdout
        run_id = str(probe.envelope["run_id"])
        record["run_id"] = run_id
        scan = cli.run("scan", product, "--run", run_id, "--only", operation, timeout=900)
        record["scan_exit"] = scan.code
        record["scan"] = json.loads((cli.runs / run_id / "scan.json").read_text(encoding="utf-8"))
        record["rule_stats"] = json.loads(
            (cli.runs / run_id / "rule-stats.json").read_text(encoding="utf-8")
        )
        view = ZapHistory(cli.state_file())
        base = "http://clinica-piloto:8080" if product == "clinica-piloto" else "http://vampi:5000"
        record["vectors"] = summarize_messages(view.all_messages(base))
        record["engine"] = view._get("/JSON/core/view/version/")
        record["addons"] = view._get("/JSON/autoupdate/view/installedAddons/")
        record["proxy_decisions"] = [
            {key: row.get(key) for key in ("decision", "reason", "status", "method")}
            for row in proxy_audit(cli)
        ]
        assert scan.code == 0, scan.stdout
        assert record["scan"]["entries"], "Operação não varrida; lacuna preservada"
    finally:
        record_metrics(f"v19-step0-{product}-{variant}", record)
        cli.stack_down()
