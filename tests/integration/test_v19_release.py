"""T4 única por API da V1.9, com conhecimento ativo e política completa legada."""

import time
from pathlib import Path

import pytest

from tests.integration.lab_support import proxy_audit, require_docker
from tests.integration.run_support import Scenario
from tests.integration.test_lab_strategy import _cli
from tests.integration.test_v17_performance import _install, _record
from tests.integration.v17_resources import ResourceSampler
from tests.integration.v17_zap_config import FastZapView
from tests.integration.v18_origin import collect_origins

pytestmark = [pytest.mark.integration, pytest.mark.lab_full]


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
def test_v19_preserva_varredura_completa(tmp_path: Path, product: str) -> None:
    """Captura, ativa explicitamente e executa a CLI sobre o laboratório descartável.

    Preparação e coleta permanecem no mesmo ciclo para preservar a evidência antes
    da desmontagem. Nenhuma exclusão ou conta é escolhida pelo gabarito.
    """
    require_docker()
    cli = _cli(tmp_path, product)
    _install(cli, product, "A")
    try:
        up = cli.run("stack", "up", product, "--build", timeout=900)
        assert up.code == 0, up.stdout + up.stderr
        captured = cli.run("knowledge", "capture", product)
        assert captured.code == 0, captured.stdout + captured.stderr
        assert captured.data["activated"] is False
        folder = cli.products / product
        (folder / "knowledge.captured.yml").rename(folder / "knowledge.yml")
        started = time.monotonic()
        with ResourceSampler(zap=FastZapView(cli.state_file())) as sampler:
            result = cli.run("run", product, timeout=3600)
        run_id = str(result.data.get("run_id") or result.envelope.get("run_id") or "")
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
        from tests.integration.run_support import record_metrics

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
        cli.stack_down()
