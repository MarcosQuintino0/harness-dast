"""Integração offline de reserva de mutações no emissor do probe."""

from pathlib import Path

import pytest

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.application.probe import Probe, ProbeRequest
from harness_dast.domain.errors import ConfigError, HarnessError, TargetTimeout
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.probe_ports import InMemorySpecs
from tests.fakes.rig import Rig, agenda_flows, default_handler


def _probe(rig: Rig, directory: Path) -> Probe:
    return Probe(
        profiles=rig.profiles,
        specs=InMemorySpecs(rig.spec),
        documents=rig.documents,
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        zap=rig.zap,
        store=rig.store,
        clock=rig.clock,
        sleeper=rig.clock,
        entropy=rig.entropy,
        value_sources=GeneratorCatalogue,
        harness_version="test",
        mutation_journal=FileMutationJournal(directory),
    )


def test_timeout_apos_intencao_impede_repeticao_em_novo_probe(tmp_path: Path) -> None:
    rig = Rig(flows=agenda_flows())

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        if request.operation_id == "criar":
            assert len(list(tmp_path.glob("*.jsonl"))) == 1
            return TargetTimeout("timeout")
        return default_handler(request, jar)

    rig.target._handler = handler
    first = _probe(rig, tmp_path).execute(ProbeRequest(product="agenda", only=("criar",)))
    assert first.operations[0].outcome == "timeout"
    count = len([request for request in rig.target.requests if request.operation_id == "criar"])
    other = Rig(flows=agenda_flows())
    with pytest.raises(ConfigError):
        _probe(other, tmp_path).execute(ProbeRequest(product="agenda", only=("criar",)))
    assert count == 1
    assert all(request.operation_id != "criar" for request in other.target.requests)
