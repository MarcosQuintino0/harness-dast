"""A auditoria distingue uma pendência recusada de uma tentativa enviada."""

from pathlib import Path

from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.errors import HarnessError, TargetTimeout
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.knowledge_mutation import MutationPending
from tests.fakes.rig import Rig, agenda_flows, default_handler
from tests.unit.application.test_knowledge_probe_journal import _probe


def test_pendencia_e_auditada_como_recusa_sem_resultado(tmp_path: Path) -> None:
    first = Rig(flows=agenda_flows())

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        if request.operation_id == "criar":
            return TargetTimeout("timeout")
        return default_handler(request, jar)

    first.target._handler = handler
    _probe(first, tmp_path).execute(ProbeRequest(product="agenda", only=("criar",)))
    second = Rig(flows=agenda_flows())
    error_message = None
    try:
        _probe(second, tmp_path).execute(ProbeRequest(product="agenda", only=("criar",)))
    except MutationPending as error:
        # A integração do estágio pode tratar a pendência e preservar o resultado parcial.
        error_message = error.message
    assert error_message is None or "resultado desconhecido" in error_message
    rows = [entry for entry in second.store.all_audit() if entry.operation_id == "criar"]
    assert len(rows) == 1
    assert (rows[0].phase, rows[0].decision, rows[0].reason) == (
        "decision",
        "denied",
        "mutation_pending",
    )
    assert all(request.operation_id != "criar" for request in second.target.requests)
