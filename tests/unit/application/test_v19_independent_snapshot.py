"""Verificação independente da intenção persistida antes da escrita."""

import json
from pathlib import Path

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.application.authz import AuthzRequest
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.authz_rig import Clinic
from tests.fakes.probe_ports import FakeTarget, reply
from tests.unit.application.test_authz_journal_snapshot import _service
from tests.unit.application.test_authz_mass_derived import derived_rig


def test_v19_independent_snapshot_is_persisted_before_send_and_retained_after_500(
    tmp_path: Path,
) -> None:
    rig = derived_rig(
        Clinic(stores=("saldo",)),
        derive_mass_candidates=False,
        mass_assignment_fields=[{"name": "saldo", "value": 11}],
    )
    probe = rig.run_probe()
    delegate = rig.clinic
    seen: list[dict[str, object]] = []

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id == "authz:atualizarPerfil" and request.method == "PUT":
            files = list(tmp_path.glob("*.jsonl"))
            assert len(files) == 1
            record = json.loads(files[0].read_text(encoding="utf-8"))
            seen.append(record)
            assert record["snapshot"] == {"field": "saldo", "value": 10, "source": "observed"}
            assert record["previous_state"] == "present"
            assert request.body is not None
            assert request.body.decode() not in json.dumps(record)
            return reply(500, {})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    result = _service(rig, FileMutationJournal(tmp_path)).execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )

    assert any(n.reason == "possible_unrestored_change" for n in result.not_tested)
    assert len(seen) == 1
    pending = list(tmp_path.glob("*.jsonl"))
    assert len(pending) == 1
    assert json.loads(pending[0].read_text(encoding="utf-8")) == seen[0]
