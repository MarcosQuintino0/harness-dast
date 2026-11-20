"""Aceite independente do motor observado no fluxo de execu??o."""

import pytest

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.application.probe import Probe, ProbeRequest
from harness_dast.application.scan import Scan, ScanRequest
from harness_dast.application.scope_approval import ApprovedProfileRepository
from harness_dast.application.strategy import StrategyProfiles, basis_for_engine
from harness_dast.domain.errors import ConfigError, ExternalToolError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy import StrategyReferences
from harness_dast.domain.strategy_basis import (
    StrategyBasis,
    digest_strategy_document,
    make_strategy_basis,
)
from tests.fakes.approvals import InMemoryApprovalStore, approval_for
from tests.fakes.probe_ports import FakeTarget, FakeZap, InMemorySpecs
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.rig import Rig, agenda_flows
from tests.fakes.scan_rig import ScanRig


class _LiveStore:
    def __init__(self, data: dict[str, object] | None, docs: tuple[bytes, bytes, bytes]) -> None:
        self.data = data
        self.docs = docs

    def read(self, product: str) -> dict[str, object] | None:
        return self.data

    def check_references(self, product: str, references: StrategyReferences) -> None:
        pass

    def read_dependencies(
        self, product: str, profile: ProductProfile
    ) -> tuple[bytes, bytes | None, bytes | None]:
        return self.docs

    def migrate(self, product: str, output: str) -> str:
        raise AssertionError("migração não deve ser chamada")


class _ObservedZap:
    def __init__(self, target: FakeTarget, version: str) -> None:
        self.inner = FakeZap(version)
        self.target = target
        self.target_counts: list[int] = []

    def version(self) -> str:
        self.target_counts.append(len(self.target.requests))
        return self.inner.version()

    def start_session(self, name: str) -> None:
        self.inner.start_session(name)

    def create_context(self, name: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> int:
        return self.inner.create_context(name, include, exclude)

    def remove_stale_rules(self, prefix: str) -> int:
        return self.inner.remove_stale_rules(prefix)


def _live_probe(rig: Rig, store: _LiveStore, zap: _ObservedZap) -> Probe:
    approvals = InMemoryApprovalStore()
    approvals.write(approval_for(rig.profile))
    profiles = StrategyProfiles(
        ApprovedProfileRepository(rig.profiles, approvals), store, rig.clock, zap
    )
    return Probe(
        profiles=profiles,
        specs=InMemorySpecs(rig.spec),
        documents=rig.documents,
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        zap=zap,
        store=rig.store,
        clock=rig.clock,
        sleeper=rig.clock,
        entropy=rig.entropy,
        value_sources=GeneratorCatalogue,
        harness_version="0.0-test",
    )


def _bound_strategy(profile: ProductProfile, docs: tuple[bytes, bytes, bytes]) -> dict[str, object]:
    basis = make_strategy_basis(
        profile,
        openapi_sha256=digest_strategy_document(docs[0]),
        data_rules_sha256=digest_strategy_document(docs[1]),
        flows_sha256=digest_strategy_document(docs[2]),
        engine_version="2.17.0",
    )
    assert basis is not None
    return {
        "schema_version": 1,
        "references": {
            "target": "target.yml",
            "data_rules": "data-rules.yml",
            "flows": "flows.yml",
        },
        "choices": [
            {
                "name": "coverage",
                "value": "preserve",
                "source": "owner",
                "reason": "preserve_baseline",
                "state": "validated",
                "valid_until": "2999-12-31",
                "basis": basis.model_dump(),
            }
        ],
    }


@pytest.mark.parametrize("case", ["valid", "engine", "document", "unavailable", "invalid"])
def test_probe_confere_motor_e_fontes_antes_de_enviar_ao_alvo(case: str) -> None:
    rig = Rig(flows=agenda_flows())
    docs = (b"contrato", b"regras", b"fluxos")
    strategy = _bound_strategy(rig.profile, docs)
    actual_docs = (b"alterado", docs[1], docs[2]) if case == "document" else docs
    versions = {"engine": "2.18", "invalid": "\x00segredo-sentinela"}
    zap = _ObservedZap(rig.target, versions.get(case, "2.17.0"))
    if case == "unavailable":
        zap.inner.fail = ExternalToolError("motor indisponível")
    probe = _live_probe(rig, _LiveStore(strategy, actual_docs), zap)

    if case == "valid":
        probe.execute(ProbeRequest(product="agenda"))
        assert rig.target.requests
    else:
        with pytest.raises((ConfigError, ExternalToolError)) as caught:
            probe.execute(ProbeRequest(product="agenda"))
        assert "segredo-sentinela" not in str(caught.value)
        assert rig.target.requests == []
    assert zap.target_counts[0] == 0


def test_probe_vazio_equivale_a_ausencia_sem_consulta_extra_do_motor() -> None:
    outcomes: list[tuple[object, object, int]] = []
    for present in (False, True):
        rig = Rig(flows=agenda_flows())
        zap = _ObservedZap(rig.target, "2.17.0")
        empty = _bound_strategy(rig.profile, (b"", b"", b"")) if present else None
        if empty is not None:
            empty["choices"] = []
        result = _live_probe(rig, _LiveStore(empty, (b"", b"", b"")), zap).execute(
            ProbeRequest(product="agenda", seed=7)
        )
        outcomes.append((result, rig.target.requests, len(zap.target_counts)))

    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("valid", [True, False])
def test_scan_compila_snapshot_com_motor_atual_antes_do_alvo(valid: bool) -> None:
    rig = ScanRig(flows=agenda_flows())
    probe = rig.run_probe()
    rig.target.requests.clear()
    docs = (b"contrato", b"regras", b"fluxos")
    data = _bound_strategy(rig.profile, docs)
    store = _LiveStore(data, docs if valid else (b"contrato alterado", docs[1], docs[2]))
    approvals = InMemoryApprovalStore()
    approvals.write(approval_for(rig.profile))
    profiles = StrategyProfiles(
        ApprovedProfileRepository(rig.profiles, approvals), store, rig.clock, rig.zap
    )
    scan = Scan(
        profiles=profiles,
        specs=rig._specs(),
        documents=rig.documents,
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        zap=rig.zap,
        scanner=rig.scanner,
        store=rig.store,
        artifacts=rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
        strategy_store=store,
        approvals=approvals,
        basis_for=lambda product, profile, version: basis_for_engine(
            store, product, profile, version
        ),
    )

    if valid:
        result = scan.execute(ScanRequest(product="agenda", run_id=probe.run_id))
        assert result.status == "completed"
        assert rig.zap.started
    else:
        with pytest.raises(ConfigError):
            scan.execute(ScanRequest(product="agenda", run_id=probe.run_id))
        assert rig.zap.started == []
        assert rig.target.requests == []


def test_configuracao_de_limpeza_nao_muda_vinculo_de_cobertura() -> None:
    profile_data = valid_profile_data()
    digest = digest_strategy_document(b"conteudo")

    def basis() -> StrategyBasis | None:
        return make_strategy_basis(
            ProductProfile.from_data(profile_data),
            openapi_sha256=digest,
            data_rules_sha256=digest,
            flows_sha256=digest,
            engine_version="2.17",
        )

    original = basis()
    profile_data["cleanup"] = valid_profile_data(with_cleanup=True)["cleanup"]

    assert original is not None
    assert basis() == original
