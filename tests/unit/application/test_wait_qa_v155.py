"""Corridas e isolamento da espera local."""

from pathlib import Path

from harness_dast.adapters.reporting.wait_files import FileWaitReader, ProductWaitReader
from harness_dast.adapters.reporting.wait_marker import FileWaitMarker
from harness_dast.application.stack_models import StackLockInfo
from tests.unit.domain.panel_helpers import run_summary

RUN_ID = "2026-11-13T10-00-00Z-demo-aaaa"


def test_leitura_reconfere_resultado_apos_trava_desaparecer(tmp_path: Path) -> None:
    directory = tmp_path / RUN_ID
    directory.mkdir()

    def finish() -> None:
        summary = run_summary(run_id=RUN_ID, product="demo")
        (directory / "run.json").write_text(summary.model_dump_json(), encoding="utf-8")
        return None

    assert FileWaitReader(tmp_path, finish).read(RUN_ID).state == "finished"


def test_espera_de_tomada_antiga_nao_confunde_trava_posterior(tmp_path: Path) -> None:
    FileWaitMarker(tmp_path, "aabbccdd").write("probe", None)
    new_lock = StackLockInfo(
        state="held", command="run", product="demo", lock_id="deadbeef", message="ativo"
    )

    result = ProductWaitReader(tmp_path, lambda: new_lock, "aabbccdd").read("demo")

    assert result.state == "stopped"
    assert result.lock_id == "aabbccdd"
