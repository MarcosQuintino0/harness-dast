"""Executa somente T4 B nas duas APIs usando o suporte e as travas V1.7."""

import json
import os
from pathlib import Path

import pytest

from tests.integration.test_v17_performance import _exercise
from tests.integration.v18_origin import collect_origins

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
def test_v18_t4_proxy(tmp_path: Path, product: str) -> None:
    _exercise(tmp_path, product, "B", "t4", 1)
    path = Path(os.environ["HDAST_IT_METRICS_DIR"]) / f"v17-t4-{product}-vulnerable-1-B.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    run_id = record["manifest"]["run_id"]
    origins = collect_origins(tmp_path / "runs" / run_id)
    destination = path.with_name(path.stem + "-origins.json")
    with destination.open("x", encoding="utf-8") as output:
        json.dump(origins, output, ensure_ascii=False, indent=2)
    assert all(source["status"] != "ausente" for source in origins["sources"].values())
    assert record["exit_code"] == 0
    assert record["scan"]["status"] == "completed"
    assert record["scan"]["entries"]
    assert all(
        entry["outcome"] == "completed" and not entry["truncated"]
        for entry in record["scan"]["entries"]
    )
