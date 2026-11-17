"""Diário durável nos caminhos mutantes do negative e do scan."""

from pathlib import Path

import pytest

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.application.negative import Negative, NegativeRequest
from harness_dast.application.ports import ProfileRepository, ReferencedFile
from harness_dast.application.scan import Scan, ScanRequest
from harness_dast.domain.errors import ConfigError, ExternalToolError
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.knowledge_mutation import mutation_key
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scan_result import ScanResult
from tests.fakes.negative_rig import CREATE, PRICE, PRODUCTS, UPDATE, Catalog, NegativeRig, exchange
from tests.fakes.probe_ports import FakeTarget
from tests.fakes.rig import operation
from tests.fakes.scan_ports import InMemoryRunArtifacts
from tests.unit.application.authz.test_created_pair import execute, make_rig
from tests.unit.application.test_scan import ready


def negative_service(
    rig: NegativeRig, journal: FileMutationJournal, profiles: ProfileRepository | None = None
) -> Negative:
    return Negative(
        profiles=profiles or rig.profiles,
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


def scan_service(
    rig: object,
    journal: FileMutationJournal,
    artifacts: object = None,
    profiles: ProfileRepository | None = None,
) -> Scan:
    from tests.fakes.scan_rig import ScanRig

    assert isinstance(rig, ScanRig)
    assert artifacts is None or isinstance(artifacts, InMemoryRunArtifacts)
    return Scan(
        profiles=profiles or rig.profiles,
        specs=rig._specs(),
        documents=rig.documents,
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        zap=rig.zap,
        scanner=rig.scanner,
        store=rig.store,
        artifacts=artifacts or rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
        mutation_journal=journal,
    )


class ChangedBasis:
    def __init__(self, wrapped: ProfileRepository) -> None:
        self.wrapped = wrapped
        self.loads = 0

    def load(self, product: str) -> ProductProfile:
        self.loads += 1
        if self.loads > 1:
            raise ConfigError("Fonte de conhecimento mudou")
        return self.wrapped.load(product)

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        return self.wrapped.missing_files(product, profile)


def test_negative_recusa_base_alterada_antes_de_enviar(tmp_path: Path) -> None:
    rig = NegativeRig(allow_writes=True)
    probe = rig.seed(CREATE)
    with pytest.raises(ConfigError, match="conhecimento mudou"):
        negative_service(rig, FileMutationJournal(tmp_path), ChangedBasis(rig.profiles)).execute(
            NegativeRequest(product="agenda", run_id=probe.run_id)
        )
    assert rig.sent() == []


def test_scan_recusa_base_alterada_antes_de_iniciar(tmp_path: Path) -> None:
    rig = ready()
    with pytest.raises(ConfigError, match="conhecimento mudou"):
        scan_service(
            rig, FileMutationJournal(tmp_path), profiles=ChangedBasis(rig.profiles)
        ).execute(ScanRequest(product="agenda", run_id=rig.probe_result.run_id))
    assert rig.zap.started == []


def test_authz_recusa_base_alterada_antes_de_enviar(tmp_path: Path) -> None:
    rig = make_rig("api/widgets", exposed=True)
    with pytest.raises(ConfigError, match="conhecimento mudou"):
        execute(
            rig,
            "api/widgets",
            journal=FileMutationJournal(tmp_path),
            profiles=ChangedBasis(rig.profiles),
        )
    assert not [r for r in rig.target.requests if r.operation_id.startswith("authz:")]


def test_negative_dry_run_nao_cria_diario(tmp_path: Path) -> None:
    rig = NegativeRig(allow_writes=True)
    probe = rig.seed(CREATE)
    path = tmp_path / "diario"
    result = negative_service(rig, FileMutationJournal(path)).execute(
        NegativeRequest(product="agenda", run_id=probe.run_id, dry_run=True)
    )
    assert result.dry_run
    assert not path.exists()
    assert rig.sent() == []


def test_scan_dry_run_nao_cria_diario(tmp_path: Path) -> None:
    rig = ready()
    path = tmp_path / "diario"
    result = scan_service(rig, FileMutationJournal(path)).execute(
        ScanRequest(product="agenda", run_id=rig.probe_result.run_id, dry_run=True)
    )
    assert result.dry_run
    assert not path.exists()
    assert rig.zap.started == []


def test_negative_reserva_invalida_bloqueia_antes_da_escrita(tmp_path: Path) -> None:
    rig = NegativeRig(allow_writes=True)
    probe = rig.seed(CREATE)
    journal = FileMutationJournal(tmp_path)
    journal.begin(mutation_key("agenda", CREATE.operation_id, CREATE.account, "POST"), "unknown")
    result = negative_service(rig, journal).execute(
        NegativeRequest(product="agenda", run_id=probe.run_id)
    )
    assert result.status == "stopped_zap"
    assert any(n.reason == "mutation_outcome_unknown" for n in result.not_tested)
    assert rig.sent("POST") == []


def test_negative_500_mantem_pendencia_sem_reenviar(tmp_path: Path) -> None:
    rig = NegativeRig(Catalog(mode="crash"), allow_writes=True)
    probe = rig.seed(CREATE)
    journal = FileMutationJournal(tmp_path)
    result = negative_service(rig, journal).execute(
        NegativeRequest(product="agenda", run_id=probe.run_id)
    )
    assert result.status == "stopped_zap"
    assert any(n.reason == "mutation_outcome_unknown" for n in result.not_tested)
    assert any(f.technique == "input_server_error" for f in result.findings)
    assert len(rig.sent("POST")) == 1
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_negative_falha_de_transporte_apos_envio_mantem_pendencia(tmp_path: Path) -> None:
    rig = NegativeRig(allow_writes=True)
    probe = rig.seed(CREATE)
    delegate = rig.catalog

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id.startswith("negative:") and request.method == "POST":
            raise ExternalToolError("Falha após possível envio")
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    result = negative_service(rig, FileMutationJournal(tmp_path)).execute(
        NegativeRequest(product="agenda", run_id=probe.run_id)
    )
    assert result.status == "stopped_zap"
    assert len(rig.sent("POST")) == 1
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_negative_registra_tambem_restauracao(tmp_path: Path) -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)
    probe = rig.seed(UPDATE)
    journal = FileMutationJournal(tmp_path)
    negative_service(rig, journal).execute(NegativeRequest(product="agenda", run_id=probe.run_id))
    writes = rig.sent("PUT")
    assert any("restore:" in request.operation_id for request in writes)
    assert len(list((tmp_path / "completed").glob("*.jsonl"))) == len(writes)
    assert not list(tmp_path.glob("*.jsonl"))


def test_negative_preserva_achado_quando_500_bloqueia_restauracao(tmp_path: Path) -> None:
    rig = NegativeRig(Catalog(mode="crash"), allow_writes=True)
    probe = rig.seed(UPDATE)
    result = negative_service(rig, FileMutationJournal(tmp_path)).execute(
        NegativeRequest(product="agenda", run_id=probe.run_id)
    )
    assert result.status == "stopped_zap"
    assert any(f.technique == "input_server_error" and f.restored is False for f in result.findings)
    assert {"possible_unrestored_change", "mutation_outcome_unknown"} <= {
        n.reason for n in result.not_tested
    }
    assert len(rig.sent("PUT")) == 1
    assert rig.artifacts.negative[probe.run_id] == result


def test_negative_grava_projecao_baseline_antes_do_envio_incerto(tmp_path: Path) -> None:
    import json

    rig = NegativeRig(Catalog(mode="crash"), allow_writes=True)
    create = operation("criarProduto", "post", PRODUCTS, body={"preco": PRICE}, required=("preco",))
    rig.spec = rig.spec.model_copy(
        update={
            "operations": tuple(
                create if op.operation_id == "criarProduto" else op for op in rig.spec.operations
            )
        }
    )
    prior = exchange("criarProduto", "POST", PRODUCTS, PRODUCTS, body={"preco": 5}, status=201)
    probe = rig.seed(prior)
    result = negative_service(rig, FileMutationJournal(tmp_path)).execute(
        NegativeRequest(product="agenda", run_id=probe.run_id)
    )
    assert result.status == "stopped_zap"
    pending = list(tmp_path.glob("*.jsonl"))
    assert len(pending) == 1
    record = json.loads(pending[0].read_text(encoding="utf-8"))
    assert record["previous_state"] == "unknown"
    assert record["snapshot"] == {"field": "preco", "value": 5, "source": "request_baseline"}


def test_scan_pendencia_recusa_antes_de_iniciar_zap(tmp_path: Path) -> None:
    rig = ready()
    account = next(r.account for r in rig.target.requests if r.operation_id == "criar")
    journal = FileMutationJournal(tmp_path)
    journal.begin(mutation_key("agenda", "criar", account, "POST"), "unknown")
    result = scan_service(rig, journal).execute(
        ScanRequest(product="agenda", run_id=rig.probe_result.run_id, only=("criar",))
    )
    assert result.status == "stopped_zap"
    assert rig.artifacts.scans[rig.probe_result.run_id] == result
    assert rig.zap.started == []


def test_scan_falha_apos_envio_mantem_intencao(tmp_path: Path) -> None:
    rig = ready()
    rig.zap.failures["scan_status"] = ExternalToolError("interrompido")
    journal = FileMutationJournal(tmp_path)
    result = scan_service(rig, journal).execute(
        ScanRequest(product="agenda", run_id=rig.probe_result.run_id, only=("criar",))
    )
    assert result.status == "stopped_zap"
    assert len(rig.zap.started) == 1
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


class BrokenArtifacts(InMemoryRunArtifacts):
    def write_scan(self, run_id: str, result: ScanResult) -> None:
        raise ConfigError("Falha ao persistir scan")


def test_scan_falha_ao_gravar_resultado_mantem_intencao(tmp_path: Path) -> None:
    rig = ready()
    journal = FileMutationJournal(tmp_path)
    with pytest.raises(ConfigError, match="persistir"):
        scan_service(rig, journal, BrokenArtifacts(rig.store)).execute(
            ScanRequest(product="agenda", run_id=rig.probe_result.run_id, only=("criar",))
        )
    assert len(rig.zap.started) == 1
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_scan_concluido_so_libera_apos_gravar_resultado(tmp_path: Path) -> None:
    rig = ready()
    journal = FileMutationJournal(tmp_path)
    result = scan_service(rig, journal).execute(
        ScanRequest(product="agenda", run_id=rig.probe_result.run_id, only=("criar",))
    )
    assert result.status == "completed"
    assert not list(tmp_path.glob("*.jsonl"))
    assert len(list((tmp_path / "completed").glob("*.jsonl"))) == 1


@pytest.mark.parametrize(("state", "progress"), [("FINISHED", 99), ("STOPPED", 100)])
def test_scan_incompleto_nao_libera_intencao(tmp_path: Path, state: str, progress: int) -> None:
    rig = ready()
    rig.zap.script = [(progress, state)]
    journal = FileMutationJournal(tmp_path)
    result = scan_service(rig, journal).execute(
        ScanRequest(product="agenda", run_id=rig.probe_result.run_id, only=("criar",))
    )
    assert len(result.entries) == 1
    assert result.entries[0].progress == progress
    assert "pendente" in (result.entries[0].note or "")
    assert len(list(tmp_path.glob("*.jsonl"))) == 1
    assert not list((tmp_path / "completed").glob("*.jsonl"))


def test_scan_recusado_mantem_intencao_sem_prova_independente(tmp_path: Path) -> None:
    rig = ready()
    rig.zap.refuse = frozenset({"POST"})
    result = scan_service(rig, FileMutationJournal(tmp_path)).execute(
        ScanRequest(product="agenda", run_id=rig.probe_result.run_id, only=("criar",))
    )
    assert result.entries[0].outcome == "refused"
    assert "pendente" in (result.entries[0].note or "")
    assert rig.zap.started == []
    assert len(list(tmp_path.glob("*.jsonl"))) == 1
