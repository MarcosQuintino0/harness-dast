"""T4 única por API da V1.9, com conhecimento ativo e política completa legada."""

import time
from pathlib import Path

import pytest

from tests.integration.finding_origin_support import collect_origins
from tests.integration.lab_support import CliResult, LabCli, proxy_audit, require_docker
from tests.integration.performance_resources_support import ResourceSampler
from tests.integration.run_support import Scenario, record_metrics
from tests.integration.test_lab_strategy import _cli
from tests.integration.test_scan_performance_matrix import _install, _record
from tests.integration.zap_scan_readback_support import FastZapView

pytestmark = [pytest.mark.integration, pytest.mark.lab_full]


def _command(
    cli: LabCli, stages: list[dict[str, object]], *args: str, timeout: int = 900
) -> CliResult:
    result = cli.run(*args, timeout=timeout)
    stages.append({"command": args[0], "exit_code": result.code})
    assert result.code in {0, 1} if args[0] == "report" else result.code == 0, result.stdout
    return result


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
def test_v19_preserva_varredura_completa(tmp_path: Path, product: str) -> None:
    """Captura, ativa explicitamente e executa a CLI sobre o laboratório descartável.

    Preparação e coleta permanecem no mesmo ciclo para preservar a evidência antes
    da desmontagem. Nenhuma exclusão ou conta é escolhida pelo gabarito.
    """
    require_docker()
    cli = _cli(tmp_path, product)
    _install(cli, product, "A")
    stages: list[dict[str, object]] = []
    try:
        up = cli.stack_up(product, timeout=900)
        assert up.code == 0, up.stdout + up.stderr
        started = time.monotonic()
        _command(cli, stages, "preflight", product)
        probe = _command(cli, stages, "probe", product)
        run_id = str(probe.envelope["run_id"])
        captured = _command(cli, stages, "knowledge", "capture", product, "--run", run_id)
        assert captured.data["activated"] is False
        folder = cli.products / product
        (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")
        with ResourceSampler(zap=FastZapView(cli.state_file())) as sampler:
            _command(cli, stages, "scan", product, "--run", run_id, timeout=3600)
        _command(cli, stages, "authz", product, "--run", run_id)
        _command(cli, stages, "negative", product, "--run", run_id)
        result = _command(cli, stages, "report", product, "--run", run_id)
        scenario = Scenario(
            f"v19-t4-{product}",
            cli,
            result,
            cli.runs / run_id,
            proxy_audit(cli),
            dict(sampler.peaks),
            time.monotonic() - started,
        )
        _record(scenario, product, "A", "t4", "vulnerable", sampler)
        record_metrics(f"v19-t4-{product}-origins", collect_origins(scenario.run_dir))
        assert result.code in {0, 1}, result.stdout + result.stderr
        scan = scenario.load("scan.json")
        assert scan["status"] == "completed"
        assert scan["entries"]
        assert all(
            row["outcome"] == "completed" and not row["truncated"] for row in scan["entries"]
        )
        assert scan["traffic"]["allowed_outside_allow"] == 0
        assert not any(row["method"] == "DELETE" for row in scenario.audit)
    finally:
        record_metrics(f"v19-t4-{product}-stages", {"product": product, "stages": stages})
        cli.stack_down()
