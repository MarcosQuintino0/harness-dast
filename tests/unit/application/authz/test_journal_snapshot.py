"""O diário guarda apenas a projeção anterior já observada antes da escrita."""

import json
from pathlib import Path

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.application.authz.service import Authz, AuthzRequest
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.authz.rig import AuthzRig, Clinic
from tests.fakes.probe_ports import FakeTarget, reply
from tests.unit.application.authz.test_mass_derived import derived_rig


def test_mass_grava_campo_observado_antes_de_envio_com_resultado_500(tmp_path: Path) -> None:
    rig = derived_rig(
        Clinic(stores=("saldo",)),
        derive_mass_candidates=False,
        mass_assignment_fields=[{"name": "saldo", "value": 11}],
    )
    probe = rig.run_probe()
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id == "authz:atualizarPerfil" and request.method == "PUT":
            return reply(500, {})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    result = _service(rig, FileMutationJournal(tmp_path)).execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )
    assert result.findings == ()
    pending = list(tmp_path.glob("*.jsonl"))
    assert len(pending) == 1
    record = json.loads(pending[0].read_text(encoding="utf-8"))
    assert record["metadata"]["run_id"] == probe.run_id
    assert record["metadata"]["operation_id"] == "atualizarPerfil"
    assert record["metadata"]["method"] == "PUT"
    assert record["previous_state"] == "present"
    assert record["snapshot"] == {"field": "saldo", "value": 10, "source": "observed"}


def _service(rig: AuthzRig, journal: FileMutationJournal) -> Authz:
    return Authz(
        profiles=rig.profiles,
        specs=rig._specs(),
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        store=rig.store,
        artifacts=rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
        mutation_journal=journal,
    )
