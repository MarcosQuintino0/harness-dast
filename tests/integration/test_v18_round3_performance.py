"""Quatro medições T4 da rodada 3, com origens sanitizadas separadas."""

import json
import os
from pathlib import Path

import pytest

from tests.integration.test_v17_performance import _exercise
from tests.integration.v18_origin import collect_origins

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
@pytest.mark.parametrize("variant", ["A", "B"])
def test_v18_t4_round3(tmp_path: Path, product: str, variant: str) -> None:
    _exercise(tmp_path, product, variant, "t4", 1)
    path = (
        Path(os.environ["HDAST_IT_METRICS_DIR"]) / f"v17-t4-{product}-vulnerable-1-{variant}.json"
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    run_id = record["manifest"]["run_id"]
    origins = collect_origins(tmp_path / "runs" / run_id)
    with path.with_name(path.stem + "-origins.json").open("x", encoding="utf-8") as output:
        json.dump(origins, output, ensure_ascii=False, indent=2)
    assert all(source["status"] != "ausente" for source in origins["sources"].values())
    assert record["exit_code"] == 0
    assert record["scan"]["status"] == "completed"
    assert record["scan"]["entries"]
    assert all(
        e["outcome"] == "completed" and not e["truncated"] for e in record["scan"]["entries"]
    )
