"""Verifica captura da origem e ausência explícita de estágio."""

import json
from pathlib import Path

from tests.integration.v18_origin import collect_origins


def test_collect_origins_separates_sources_and_does_not_copy_evidence(tmp_path: Path) -> None:
    for name, title in (("findings.json", "ZAP"), ("authz.json", "authz")):
        (tmp_path / name).write_text(
            json.dumps(
                {"run_id": tmp_path.name, "findings": [{"title": title, "evidence": "privado"}]}
            ),
            encoding="utf-8",
        )
    result = collect_origins(tmp_path)
    assert result["sources"]["zap"]["findings"][0]["title"] == "ZAP"
    assert result["sources"]["authz"]["findings"][0]["title"] == "authz"
    assert result["sources"]["negative"]["status"] == "ausente"
    assert "privado" not in json.dumps(result)
