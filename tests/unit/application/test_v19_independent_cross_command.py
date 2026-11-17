"""Contrato independente do diário compartilhado entre probe e scan."""

from pathlib import Path

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.application.probe import ProbeRequest
from harness_dast.application.scan import ScanRequest
from harness_dast.domain.errors import HarnessError, TargetTimeout
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.rig import Rig, agenda_flows, default_handler
from tests.unit.application.test_knowledge_probe_journal import _probe
from tests.unit.application.test_scan import ready
from tests.unit.application.test_v19_mutation_stages import scan_service


def test_v19_independent_probe_timeout_blocks_same_scan(tmp_path: Path) -> None:
    first = Rig(flows=agenda_flows())

    def timeout(request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        if request.operation_id == "criar":
            return TargetTimeout("timeout")
        return default_handler(request, jar)

    first.target._handler = timeout
    result = _probe(first, tmp_path).execute(ProbeRequest(product="agenda", only=("criar",)))
    assert result.operations[0].outcome == "timeout"
    sent = next(r for r in first.target.requests if r.operation_id == "criar")
    scan = ready()
    previous = next(r for r in scan.target.requests if r.operation_id == "criar")
    assert (sent.account, sent.method) == (previous.account, previous.method)

    scanned = scan_service(scan, FileMutationJournal(tmp_path)).execute(
        ScanRequest(product="agenda", run_id=scan.probe_result.run_id, only=("criar",))
    )

    assert scanned.status == "stopped_zap"
    assert not scan.zap.started
    pending = list(tmp_path.glob("*.jsonl"))
    assert len(pending) == 1
    assert (sent.body or b"").decode() not in pending[0].read_text(encoding="utf-8")


def test_v19_independent_probe_timeout_blocks_same_negative(tmp_path: Path) -> None:
    from harness_dast.application.negative import NegativeRequest
    from tests.fakes.negative_rig import CREATE, NegativeRig
    from tests.unit.application.test_v19_mutation_stages import negative_service

    first = NegativeRig(allow_writes=True)
    delegate = first.catalog

    def timeout(request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        if request.operation_id == CREATE.operation_id:
            return TargetTimeout("timeout")
        return delegate(request, jar)

    first.target._handler = timeout
    result = _probe(first, tmp_path).execute(
        ProbeRequest(product="agenda", only=(CREATE.operation_id,))
    )
    assert result.operations[0].outcome == "timeout"
    sent = next(r for r in first.target.requests if r.operation_id == CREATE.operation_id)
    assert (sent.account, sent.method) == (CREATE.account, CREATE.method)
    second = NegativeRig(allow_writes=True)
    probe = second.seed(CREATE)
    scanned = negative_service(second, FileMutationJournal(tmp_path)).execute(
        NegativeRequest(product="agenda", run_id=probe.run_id)
    )

    assert scanned.status == "stopped_zap"
    assert any(n.reason == "mutation_outcome_unknown" for n in scanned.not_tested)
    assert second.sent("POST") == []
    pending = list(tmp_path.glob("*.jsonl"))
    assert len(pending) == 1
    assert (sent.body or b"").decode() not in pending[0].read_text(encoding="utf-8")


def test_v19_independent_probe_timeout_blocks_same_authz(tmp_path: Path) -> None:
    from tests.unit.application.authz.test_created_pair import execute, make_rig

    first = make_rig("api/widgets", exposed=True)
    delegate = first.clinic

    def timeout(request: HttpRequest, jar: dict[str, str]) -> HttpResponse | HarnessError:
        if request.operation_id == "createSynthetic":
            return TargetTimeout("timeout")
        return delegate(request, jar)

    first.target._handler = timeout
    result = _probe(first, tmp_path).execute(
        ProbeRequest(product="agenda", only=("createSynthetic",), account="pac_a")
    )
    assert result.operations[0].outcome == "timeout"
    sent = next(r for r in first.target.requests if r.operation_id == "createSynthetic")
    assert (sent.account, sent.method) == ("pac_a", "POST")
    second = make_rig("api/widgets", exposed=True)
    checked = execute(second, "api/widgets", journal=FileMutationJournal(tmp_path))

    assert checked.status == "stopped_zap"
    assert any(n.reason == "mutation_outcome_unknown" for n in checked.not_tested)
    assert not [r for r in second.target.requests if r.operation_id == "authz:pair:createSynthetic"]
    pending = list(tmp_path.glob("*.jsonl"))
    assert len(pending) == 1
    assert (sent.body or b"").decode() not in pending[0].read_text(encoding="utf-8")


def test_v19_independent_unrelated_account_does_not_block_scan(tmp_path: Path) -> None:
    from harness_dast.domain.knowledge_mutation import mutation_key

    journal = FileMutationJournal(tmp_path)
    journal.begin(mutation_key("agenda", "criar", "outra-conta", "POST"), "unknown")
    scan = ready()
    sent = next(r for r in scan.target.requests if r.operation_id == "criar")
    assert sent.account != "outra-conta"

    result = scan_service(scan, journal).execute(
        ScanRequest(product="agenda", run_id=scan.probe_result.run_id, only=("criar",))
    )

    assert result.status == "completed"
    assert len(scan.zap.started) == 1
    assert len(list(tmp_path.glob("*.jsonl"))) == 1
