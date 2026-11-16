"""Reuso entre processos independentes com alvo e motor falsos, sem rede."""

import json
import subprocess
import sys
from pathlib import Path

import yaml

from tests.fakes.rig import agenda_flows

_SCRIPT = r"""
import json
import sys
from pathlib import Path
from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeStore
from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.application.knowledge import KnowledgeProfiles
from harness_dast.application.knowledge_capture import CaptureKnowledge
from harness_dast.application.probe import Probe, ProbeRequest
from tests.fakes.approvals import InMemoryApprovalStore, approval_for
from tests.fakes.probe_ports import InMemorySpecs
from tests.fakes.rig import Rig

root = Path(sys.argv[1])
rig = Rig()
docs = FileProductDocuments(root)
deps = FileStrategyRepository(root)
store = FileKnowledgeStore(root)
if sys.argv[2] == "capture":
    approvals = InMemoryApprovalStore()
    approvals.write(approval_for(rig.profile))
    capture = CaptureKnowledge(
        rig.profiles, store, deps, approvals, rig.clock, docs,
        InMemorySpecs(rig.spec), rig.zap, "http://127.0.0.1:8080",
    )
    print(json.dumps(capture.execute("agenda")))
else:
    profiles = KnowledgeProfiles(rig.profiles, store, deps, rig.clock, rig.zap)
    probe = Probe(
        profiles=profiles, specs=InMemorySpecs(rig.spec), documents=docs,
        secrets=rig.secrets, vault=rig.vault, client=rig.target, zap=rig.zap,
        store=rig.store, clock=rig.clock, sleeper=rig.clock, entropy=rig.entropy,
        value_sources=GeneratorCatalogue, harness_version="test",
    )
    result = probe.execute(ProbeRequest(product="agenda", only=("buscar",)))
    print(json.dumps({"status": result.status,
        "operations": [x.operation_id for x in result.operations],
        "paths": rig.target.paths()}))
"""


def _process(root: Path, action: str) -> dict[str, object]:
    completed = subprocess.run(  # noqa: S603 - script fixo e argumentos de teste
        [sys.executable, "-c", _SCRIPT, str(root), action],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    result: object = json.loads(completed.stdout)
    assert isinstance(result, dict)
    return {str(key): value for key, value in result.items()}


def test_documentos_reutilizados_em_novo_processo_geram_recurso_novo(tmp_path: Path) -> None:
    folder = tmp_path / "agenda"
    folder.mkdir()
    (folder / "openapi.json").write_text("{}", encoding="utf-8")
    (folder / "data-rules.yml").write_text("schema_version: 1\nrules: []\n", encoding="utf-8")
    (folder / "flows.yml").write_text(
        yaml.safe_dump(agenda_flows().model_dump(mode="json")), encoding="utf-8"
    )
    assert _process(tmp_path, "capture")["activated"] is False
    captured = folder / "knowledge.captured.yml"
    assert '"id": 7' not in captured.read_text(encoding="utf-8")
    captured.rename(folder / "knowledge.yml")
    result = _process(tmp_path, "execute")
    assert result["status"] == "completed"
    assert result["operations"] == ["criar", "buscar"]
    paths = result["paths"]
    assert isinstance(paths, list)
    assert "/api/pacientes/7" in paths
