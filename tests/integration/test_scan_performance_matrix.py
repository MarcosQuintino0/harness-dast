"""Medições T3/T4 V1.7: somente laboratório, uma pilha limpa por execução."""

import json
import os
import time
from pathlib import Path

import pytest
import yaml

from tests.integration.lab_support import (
    PILOT_PROFILE,
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    LabCli,
    proxy_audit,
    require_docker,
    run_audit,
)
from tests.integration.performance_lifecycle_support import Lifecycle
from tests.integration.performance_matrix_support import PILOT, VAMPI
from tests.integration.performance_resources_support import ResourceSampler
from tests.integration.run_support import (
    Scenario,
    collect_facts,
    record_metrics,
    throwaway_pilot_env,
)
from tests.integration.test_lab_fast import VAMPI_ENV
from tests.integration.zap_scan_readback_support import FastZapView

pytestmark = pytest.mark.integration


def _install(cli: LabCli, product: str, variant: str) -> None:
    source = PILOT_PROFILE if product == "clinica-piloto" else VAMPI_PROFILE
    extras = () if product == "clinica-piloto" else (VAMPI_OPENAPI,)
    path = cli.install_product(product, source, extras) / "target.yml"
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    profile.setdefault("scan", {})["pacing"] = "legacy" if variant == "A" else "proxy"
    path.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")


def _record(
    scenario: Scenario,
    product: str,
    variant: str,
    layer: str,
    mode: str,
    resources: ResourceSampler,
) -> None:
    base = "http://clinica-piloto:8080" if product == "clinica-piloto" else "http://vampi:5000"
    facts = collect_facts(scenario, base, pilot=product == "clinica-piloto")
    assert not facts.secret_hits, "Segredo detectado: artefatos não publicados"
    directory = scenario.run_dir
    data = {
        name: json.loads((directory / name).read_text(encoding="utf-8"))
        for name in (
            "scan.json",
            "metrics.json",
            "rule-stats.json",
            "findings.json",
            "probe.json",
            "manifest.json",
        )
        if (directory / name).exists()
    }
    scan = data.get("scan.json", {})
    profile = yaml.safe_load(
        (scenario.cli.products / product / "target.yml").read_text(encoding="utf-8")
    )
    record_metrics(
        scenario.name,
        {
            "product": product,
            "variant": variant,
            "layer": layer,
            "mode": mode,
            "profile": {key: profile.get(key) for key in ("scope", "limits", "scan")},
            "manifest": data.get("manifest.json"),
            "probe": [
                {
                    key: operation.get(key)
                    for key in (
                        "operation_id",
                        "method",
                        "path",
                        "outcome",
                        "status",
                        "account",
                        "attempts",
                        "blocked_dependencies",
                        "preview",
                    )
                }
                for operation in data.get("probe.json", {}).get("operations", [])
            ],
            "run_seconds": scenario.seconds,
            "exit_code": scenario.result.code,
            "scan": scan,
            "metrics": data.get("metrics.json"),
            "rule_stats": data.get("rule-stats.json"),
            "findings": [
                {k: f.get(k) for k in ("title", "method", "path_template", "attribution")}
                for f in data.get("findings.json", {}).get("findings", [])
            ],
            "proxy_audit": [
                {
                    k: row.get(k)
                    for k in (
                        "ts",
                        "decision",
                        "reason",
                        "detail",
                        "host",
                        "port",
                        "method",
                        "path",
                        "query_params",
                        "status",
                        "duration_ms",
                        "waited_ms",
                        "network_ms",
                        "grant_wait_ms",
                        "signals",
                        "signal_skip",
                    )
                }
                for row in scenario.audit
            ],
            "accounts": [
                {
                    key: row.get(key)
                    for key in ("phase", "route", "decision", "operation_id", "account", "method")
                }
                for row in run_audit(scenario.cli, directory.name)
            ],
            "auth_on_scanner": facts.auth_on_scanner,
            "csrf": facts.csrf,
            "rules_left": facts.rules_left,
            "peak_memory_mib": scenario.peaks,
            "resource_sampling": {
                "interval_seconds": resources.interval,
                "observed_seconds": resources.seconds,
                "attempts": resources.attempts,
                "peak_cpu_percent": dict(resources.cpu_peaks),
                "cpu_samples": dict(resources.cpu_samples),
                "memory_samples": dict(resources.memory_samples),
                "complete": resources.complete,
            },
            "zap_config_sampling": {
                "status": "observed"
                if resources.complete and resources.zap_samples
                else "unavailable",
                "attempts": resources.zap_attempts,
                "unavailable": resources.zap_unavailable,
                "errors_by_code": dict(resources.zap_errors),
                "idle": resources.zap_idle,
                "samples": list(resources.zap_samples) if resources.complete else [],
            },
        },
    )


def _remaining(maximum: int) -> int:
    deadline = float(os.environ["HDAST_V17_DEADLINE_EPOCH"])
    remaining = int(deadline - time.time())
    if remaining < 1:
        pytest.fail("Orçamento V1.7 esgotado; interromper a prova")
    return min(maximum, remaining)


def _exercise(
    tmp_path: Path, product: str, variant: str, layer: str, index: int, mode: str = "vulnerable"
) -> None:
    assert os.environ.get("HDAST_IT_METRICS_DIR"), "Defina diretório externo de métricas"
    reserve = 600 if layer == "t3" else 1800
    if _remaining(reserve) < reserve:
        pytest.fail("Sem reserva para completar o cenário; resultado inconclusivo")
    require_docker()
    cli = LabCli(tmp_path, throwaway_pilot_env() if product == "clinica-piloto" else VAMPI_ENV)
    _install(cli, product, variant)
    name = f"v17-{layer}-{product}-{mode}-{index}-{variant}"
    lifecycle = Lifecycle(Path(os.environ["HDAST_IT_METRICS_DIR"]), name, product)
    lifecycle.before_up()
    try:
        assert (
            cli.run("stack", "up", product, "--build", f"--{mode}", timeout=_remaining(900)).code
            == 0
        )
        lifecycle.after_up()
        zap_view = FastZapView(cli.state_file())
        if layer == "t4":
            started = time.monotonic()
            with ResourceSampler(zap=zap_view) as sampler:
                result = cli.run("run", product, timeout=_remaining(3600))
            run_id = str(result.data.get("run_id") or result.envelope.get("run_id") or "")
            scenario = Scenario(
                name,
                cli,
                result,
                cli.runs / run_id,
                proxy_audit(cli),
                dict(sampler.peaks),
                time.monotonic() - started,
            )
        else:
            assert cli.run("preflight", product, timeout=_remaining(420)).code == 0
            probe = cli.run("probe", product, timeout=_remaining(900))
            assert probe.code == 0
            run_id = str(probe.envelope["run_id"])
            operations: tuple[str, ...] = PILOT if product == "clinica-piloto" else VAMPI
            if layer == "t2":
                operations = (
                    ("buscarPacientesPorNome",)
                    if product == "clinica-piloto"
                    else ("api_views.users.get_by_username",)
                )
            elif layer == "t2-path":
                operations = ("baixarDocumento",)
            flags = [part for operation in operations for part in ("--only", operation)]
            started = time.monotonic()
            with ResourceSampler(zap=zap_view) as sampler:
                result = cli.run("scan", product, "--run", run_id, *flags, timeout=_remaining(3600))
            seconds = time.monotonic() - started
            cli.run("report", product, "--run", run_id, timeout=_remaining(900))
            scenario = Scenario(
                name, cli, result, cli.runs / run_id, proxy_audit(cli), dict(sampler.peaks), seconds
            )
        _record(scenario, product, variant, layer, mode, sampler)
        if layer in {"t2", "t2-path"}:
            scan = json.loads((scenario.run_dir / "scan.json").read_text(encoding="utf-8"))
            assert scan["status"] == "completed", "Scan não concluído: controle inconclusivo"
            assert any(
                entry["operation_id"] == operations[0]
                and entry["outcome"] == "completed"
                and not entry.get("truncated", False)
                for entry in scan["entries"]
            ), "Operação não concluída: controle inconclusivo"
            stats = json.loads((scenario.run_dir / "rule-stats.json").read_text(encoding="utf-8"))
            rule_id = 6 if layer == "t2-path" else 40018
            assert any(
                rule["plugin_id"] == rule_id and rule["state"] == "completed"
                for operation in stats["operations"]
                if operation["operation_id"] == operations[0]
                for rule in operation["rules"]
            ), f"Regra {rule_id} ausente ou não concluída: controle inconclusivo"
            findings = json.loads((scenario.run_dir / "findings.json").read_text(encoding="utf-8"))
            title = "Path Traversal" if layer == "t2-path" else "SQL Injection"
            matches = [
                item
                for item in findings.get("findings", [])
                if item.get("title") == title
                and (layer != "t2-path" or item.get("path_template") == "/api/documentos/download")
            ]
            assert bool(matches) == (mode == "vulnerable"), (
                f"Controle {title} ausente ou falso positivo; registrar lacuna"
            )
    finally:
        lifecycle.down(cli)


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize(
    ("index", "variant"), [(1, "A"), (1, "B"), (2, "B"), (2, "A"), (3, "A"), (3, "B")]
)
def test_v17_t3(tmp_path: Path, product: str, index: int, variant: str) -> None:
    _exercise(tmp_path, product, variant, "t3", index)


@pytest.mark.skipif(os.environ.get("V17_EXTRA_PAIRS") != "1", reason="pares extras não solicitados")
@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize(("index", "variant"), [(4, "B"), (4, "A"), (5, "A"), (5, "B")])
def test_v17_t3_extra(tmp_path: Path, product: str, index: int, variant: str) -> None:
    _exercise(tmp_path, product, variant, "t3", index)


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("variant", ["A", "B"])
def test_v17_t4(tmp_path: Path, product: str, variant: str) -> None:
    _exercise(tmp_path, product, variant, "t4", 1)


@pytest.mark.lab_fast
@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("mode", ["vulnerable", "secure"])
@pytest.mark.parametrize("variant", ["A", "B"])
def test_v17_t2_sql(tmp_path: Path, product: str, mode: str, variant: str) -> None:
    _exercise(tmp_path, product, variant, "t2", 1, mode)


@pytest.mark.lab_fast
@pytest.mark.parametrize("mode", ["vulnerable", "secure"])
@pytest.mark.parametrize("variant", ["A", "B"])
def test_v17_t2_path(tmp_path: Path, mode: str, variant: str) -> None:
    _exercise(tmp_path, "clinica-piloto", variant, "t2-path", 1, mode)
