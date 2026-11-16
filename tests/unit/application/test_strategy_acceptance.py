"""Aceite independente da preservação da varredura planejada."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.application.probe import Probe, ProbeRequest
from harness_dast.application.scan import Scan, ScanRequest
from harness_dast.application.scope_approval import ApprovedProfileRepository
from harness_dast.application.strategy import StrategyProfiles, basis_for_engine
from harness_dast.domain.errors import ConfigError, ExternalToolError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scan_plan import ScanPlan, ScanTarget
from harness_dast.domain.scan_policy import build_limits, build_policy
from harness_dast.domain.scope_approval import ScopeApproval
from harness_dast.domain.strategy import Strategy, StrategyReferences
from harness_dast.domain.strategy_basis import (
    StrategyBasis,
    digest_strategy_document,
    make_strategy_basis,
)
from harness_dast.domain.strategy_plan import compile_scan_snapshot
from tests.fakes.approvals import InMemoryApprovalStore, approval_for
from tests.fakes.probe_ports import FakeTarget, FakeZap, InMemorySpecs
from tests.fakes.profile_data import valid_profile, valid_profile_data
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


class _ObservedZap(FakeZap):
    def __init__(self, target: FakeTarget, version: str) -> None:
        super().__init__(version)
        self.target = target
        self.target_counts: list[int] = []

    def version(self) -> str:
        self.target_counts.append(len(self.target.requests))
        return super().version()


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
        zap.fail = ExternalToolError("motor indisponível")
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
        empty = _StrategyStore(True).read("agenda") if present else None
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


@pytest.mark.parametrize(
    "factor",
    [
        "environment",
        "authorization",
        "accounts",
        "openapi",
        "data_rules",
        "flows",
        "engine",
        "probe",
    ],
)
def test_escolha_validada_rejeita_alteracao_real_de_dependencia(factor: str) -> None:
    profile_data = valid_profile_data()
    docs = {"openapi": b"contrato", "data_rules": b"regras", "flows": b"fluxos"}

    def basis(engine: str) -> StrategyBasis | None:
        return make_strategy_basis(
            ProductProfile.from_data(profile_data),
            openapi_sha256=digest_strategy_document(docs["openapi"]),
            data_rules_sha256=digest_strategy_document(docs["data_rules"]),
            flows_sha256=digest_strategy_document(docs["flows"]),
            engine_version=engine,
        )

    original = basis("2.17")
    assert original is not None
    strategy = Strategy.from_data(
        {
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
                    "basis": original.model_dump(),
                }
            ],
        }
    )
    now = datetime(2026, 11, 16, tzinfo=UTC)
    strategy.ensure_compilable(now, original)
    if factor == "environment":
        profile_data["environment"]["name"] = "outro"
    elif factor == "authorization":
        profile_data["scope"]["authorization"]["reference"] = "CHG-9999"
    elif factor == "accounts":
        profile_data["auth"]["accounts"][0]["role"] = "outro"
    elif factor == "probe":
        profile_data["probe"] = {"health_path": "/api/status"}
    elif factor in docs:
        docs[factor] += b" alterado"
    current = basis("2.18" if factor == "engine" else "2.17")

    with pytest.raises(ConfigError):
        strategy.ensure_compilable(now, current)


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


class _StrategyStore:
    def __init__(self, present: bool) -> None:
        self.present = present

    def read(self, product: str) -> dict[str, object] | None:
        if not self.present:
            return None
        return {
            "schema_version": 1,
            "references": {
                "target": "target.yml",
                "data_rules": "data-rules.yml",
                "flows": "flows.yml",
            },
            "choices": [],
        }

    def check_references(self, product: str, references: StrategyReferences) -> None:
        pass

    def migrate(self, product: str, output: str) -> str:
        raise AssertionError("migração não deve ser chamada")


def _scan_com_estrategia(present: bool) -> tuple[object, object, object]:
    rig = ScanRig(flows=agenda_flows())
    probe = rig.run_probe()
    approvals = InMemoryApprovalStore()
    approvals.write(approval_for(rig.profiles.load("agenda")))
    scan = Scan(
        profiles=rig.profiles,
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
        strategy_store=_StrategyStore(present),
        approvals=approvals,
    )
    result = scan.execute(ScanRequest(product="agenda", run_id=probe.run_id))
    return result.entries, result.skipped, (rig.zap.started, rig.zap.applied)


def test_scan_real_com_falsos_preserva_trabalho_com_estrategia() -> None:
    baseline = _scan_com_estrategia(False)

    actual = _scan_com_estrategia(True)

    assert actual == baseline


def test_revogacao_durante_scan_interrompe_job_e_grava_resultado() -> None:
    rig = ScanRig(flows=agenda_flows())
    probe = rig.run_probe()
    approvals = InMemoryApprovalStore()
    approvals.write(approval_for(rig.profiles.load("agenda")))
    rig.zap.script = [(10, "RUNNING"), (100, "FINISHED")]

    def revoke(scan_id: str, poll: int) -> None:
        if scan_id == "0" and poll == 0:
            approvals.items.clear()

    rig.zap.on_status = revoke
    scan = Scan(
        profiles=ApprovedProfileRepository(rig.profiles, approvals),
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
        strategy_store=_StrategyStore(True),
        approvals=approvals,
    )

    result = scan.execute(ScanRequest(product="agenda", run_id=probe.run_id))

    assert result.status == "stopped_window"
    assert len(rig.zap.started) == 1
    assert rig.zap.was_stopped("0") is True
    assert result.entries[0].outcome == "stopped"
    assert rig.artifacts.scans[probe.run_id] == result


def test_revogacao_apos_compilar_impede_inicio_do_job() -> None:
    class RevokedAfterCompilation(InMemoryApprovalStore):
        reads = 0

        def read(self, product: str) -> ScopeApproval | None:
            approval = super().read(product)
            self.reads += 1
            if self.reads == 2:
                self.items.clear()
            return approval

    rig = ScanRig(flows=agenda_flows())
    probe = rig.run_probe()
    approvals = RevokedAfterCompilation()
    approvals.write(approval_for(rig.profiles.load("agenda")))
    scan = Scan(
        profiles=ApprovedProfileRepository(rig.profiles, approvals),
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
        strategy_store=_StrategyStore(True),
        approvals=approvals,
    )

    result = scan.execute(ScanRequest(product="agenda", run_id=probe.run_id))

    assert result.status == "stopped_window"
    assert rig.zap.started == []
    assert rig.artifacts.scans[probe.run_id] == result


@pytest.mark.parametrize(
    "change",
    ["operation", "account", "path", "precondition"],
)
def test_recusa_alteracao_de_item_do_plano(change: str) -> None:
    profile = valid_profile()
    target = ScanTarget("operacao", "GET", "/item", 1, "https://example.test/item", None)
    baseline = ScanPlan((target,), (), ())
    alternatives = {
        "operation": replace(target, operation_id="outra-operacao"),
        "account": replace(target, account="outra-conta"),
        "path": replace(target, path="/outro-ponto"),
        "precondition": replace(target, seed_outcome="not_found"),
    }
    proposed = ScanPlan((alternatives[change],), (), ())
    policy = build_policy(profile.scan)
    limits = build_limits(profile.limits, profile.scan)

    with pytest.raises(ConfigError):
        compile_scan_snapshot(
            profile,
            approval_for(profile),
            None,
            datetime(2026, 11, 16, tzinfo=UTC),
            baseline=baseline,
            proposed=proposed,
            baseline_policy=policy,
            proposed_policy=policy,
            baseline_limits=limits,
            proposed_limits=limits,
        )


@pytest.mark.parametrize(
    "change",
    [{"strength": "HIGH"}, {"disabled_rules": (40018,)}, {"url_path_injection": False}],
)
def test_recusa_alteracao_de_politica_de_cobertura(change: dict[str, object]) -> None:
    profile = valid_profile()
    plan = ScanPlan((), (), ())
    policy = build_policy(profile.scan)
    limits = build_limits(profile.limits, profile.scan)

    with pytest.raises(ConfigError):
        compile_scan_snapshot(
            profile,
            approval_for(profile),
            None,
            datetime(2026, 11, 16, tzinfo=UTC),
            baseline=plan,
            proposed=plan,
            baseline_policy=policy,
            proposed_policy=policy.model_copy(update=change),
            baseline_limits=limits,
            proposed_limits=limits,
        )
