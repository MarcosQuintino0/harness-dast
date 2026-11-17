"""Fluxo de confirmação com cliente em memória e artefatos temporários reais."""

from pathlib import Path

import pytest

from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.verification import VerificationFile
from tests.fakes.confirmation_rig import ConfirmationRig


def test_confirma_e_persiste_quando_controle_booleano_diverge(tmp_path: Path) -> None:
    rig = ConfirmationRig(tmp_path)
    result = rig.execute()
    assert isinstance(result, VerificationFile)
    assert result.entries[0].level == "reproduced"
    assert rig.store.read() == result
    requests = [r for r in rig.rig.target.requests if r.operation_id.startswith("confirm:")]
    assert len(requests) == 5
    assert all(r.method == "GET" for r in requests)
    assert "false" not in rig.path.read_text(encoding="utf-8")


def test_trava_impede_envio_quando_acionada(tmp_path: Path) -> None:
    rig = ConfirmationRig(tmp_path, stopped=True)
    before = len(rig.rig.target.requests)
    with pytest.raises(ScopeViolation, match="KillSwitchEngaged"):
        rig.execute()
    assert rig.store.read().entries[0].level == "inconclusive"
    assert len(rig.rig.target.requests) == before


@pytest.mark.parametrize("maximum", [0, 31, -1])
def test_recusa_limite_quando_fora_do_intervalo(tmp_path: Path, maximum: int) -> None:
    rig = ConfirmationRig(tmp_path)
    before = len(rig.rig.target.requests)
    with pytest.raises(ConfigError):
        rig.execute(maximum=maximum)
    assert len(rig.rig.target.requests) == before


def test_recusa_produto_divergente_antes_de_enviar(tmp_path: Path) -> None:
    rig = ConfirmationRig(tmp_path)
    report = rig.rig.artifacts.findings[rig.run_id]
    rig.rig.artifacts.findings[rig.run_id] = report.model_copy(update={"product": "outro"})
    before = len(rig.rig.target.requests)
    with pytest.raises(ConfigError):
        rig.execute()
    assert len(rig.rig.target.requests) == before


def test_escopo_negado_nao_abre_sessao_quando_semente_esta_fora(tmp_path: Path) -> None:
    rig = ConfirmationRig(tmp_path)
    log = rig.rig.store.exchanges[rig.run_id]
    exchange = log.exchanges[0].model_copy(update={"path": "/fora", "target": "/fora?q=ok"})
    rig.rig.store.exchanges[rig.run_id] = log.model_copy(update={"exchanges": (exchange,)})
    scan = rig.rig.artifacts.scans[rig.run_id]
    entry = scan.entries[0].model_copy(update={"path": "/fora"})
    rig.rig.artifacts.scans[rig.run_id] = scan.model_copy(update={"entries": (entry,)})
    report = rig.rig.artifacts.findings[rig.run_id]
    finding = report.findings[0].model_copy(update={"path_template": "/fora"})
    rig.rig.artifacts.findings[rig.run_id] = report.model_copy(update={"findings": (finding,)})
    before = len(rig.rig.target.requests)
    result = rig.execute()
    assert isinstance(result, VerificationFile)
    assert result.entries[0].level == "not_verifiable"
    assert len(rig.rig.target.requests) == before


def test_preserva_entrada_nao_selecionada_quando_ja_existe(tmp_path: Path) -> None:
    from harness_dast.domain.verification import VerificationEntry

    rig = ConfirmationRig(tmp_path)
    old = VerificationEntry(fingerprint="b" * 64, level="likely", reason="Evidência anterior.")
    rig.store.write(
        VerificationFile(schema_version=1, product="agenda", run_id=rig.run_id, entries=(old,))
    )
    result = rig.execute(finding="a" * 64)
    assert isinstance(result, VerificationFile)
    assert old in result.entries
    assert len(result.entries) == 2


@pytest.mark.parametrize(
    ("plugin", "mode", "requests"),
    [("40022", "time", 6), ("40012", "xss", 4), ("90022", "error", 4)],
)
def test_receita_com_trafego_falso_reproduz_efeito_e_controle(
    tmp_path: Path, plugin: str, mode: str, requests: int
) -> None:
    from tests.fakes.confirmation_rig import recipe_target

    rig = ConfirmationRig(tmp_path, plugin=plugin, handler=recipe_target(mode))
    result = rig.execute()
    assert isinstance(result, VerificationFile)
    assert result.entries[0].level == "reproduced"
    assert (
        len([r for r in rig.rig.target.requests if r.operation_id.startswith("confirm:")])
        == requests
    )
    assert "synthetic error" not in rig.path.read_text(encoding="utf-8")


def test_pilha_desatualizada_para_antes_do_login(tmp_path: Path) -> None:
    from harness_dast.application.confirmation import ConfirmationRequest
    from tests.fakes.confirmation_rig import StaleProfiles

    rig = ConfirmationRig(tmp_path)
    service = rig.service(profiles=StaleProfiles(rig.rig.profiles))
    before = len(rig.rig.target.requests)
    with pytest.raises(ConfigError, match="ConfigError"):
        service.execute(ConfirmationRequest(product="agenda", run_id=rig.run_id))
    assert len(rig.rig.target.requests) == before
    assert rig.store.read().entries[0].level == "inconclusive"


def test_fluxo_com_artefatos_reais_e_cliente_falso(tmp_path: Path) -> None:
    from harness_dast.adapters.reporting.run_files import FileRunArtifacts
    from harness_dast.adapters.storage.run_store import FileRunStore
    from harness_dast.adapters.storage.verification_store import VerificationStore
    from harness_dast.application.account_session import TokenCache
    from harness_dast.application.confirmation import (
        Confirmation,
        ConfirmationDependencies,
        ConfirmationRequest,
    )

    rig = ConfirmationRig(tmp_path)
    directory = tmp_path / rig.run_id
    directory.mkdir()
    models = {
        "probe.json": rig.rig.artifacts.read_probe(rig.run_id),
        "scan.json": rig.rig.artifacts.read_scan(rig.run_id),
        "exchanges.json": rig.rig.artifacts.read_exchanges(rig.run_id),
        "findings.json": rig.rig.artifacts.read_findings(rig.run_id),
    }
    for name, model in models.items():
        (directory / name).write_text(model.model_dump_json(), encoding="utf-8")
    (directory / "audit.jsonl").write_text("", encoding="utf-8")
    verification = VerificationStore(directory / "verification.json", rig.rig.vault.mask)
    deps = ConfirmationDependencies(
        profiles=rig.rig.profiles,
        artifacts=FileRunArtifacts(tmp_path),
        verification=verification,
        existing=False,
        store=FileRunStore(tmp_path),
        client=rig.rig.target,
        secrets=rig.rig.secrets,
        vault=rig.rig.vault,
        clock=rig.rig.clock,
        sleeper=rig.rig.clock,
        kill_switch=rig.switch,
        token_cache=TokenCache(),
        marker=lambda: "0123456789abcdef",
    )
    result = Confirmation(deps).execute(ConfirmationRequest(product="agenda", run_id=rig.run_id))
    assert verification.read() == result
    assert result.entries[0].level == "reproduced"
    assert (directory / "audit.jsonl").read_text(encoding="utf-8").count("confirm:listar") == 10


def test_comparacao_authz_valida_nao_gera_novo_trafego(tmp_path: Path) -> None:
    from harness_dast.domain.authz.findings import horizontal_finding
    from harness_dast.domain.authz.result import AuthzResult

    rig = ConfirmationRig(tmp_path)
    item = horizontal_finding(
        product="agenda",
        operation_id="listar",
        method="GET",
        path_template="/api/pacientes",
        actor=("user_a", "comum"),
        owner=("user_b", "comum"),
        statuses=(200, 200),
    )
    authz = AuthzResult(
        run_id=rig.run_id,
        product="agenda",
        status="completed",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:00Z",
        findings=(item,),
    )
    report = rig.rig.artifacts.findings[rig.run_id]
    rig.rig.artifacts.findings[rig.run_id] = report.model_copy(
        update={"findings": (), "authz": authz}
    )
    before = len(rig.rig.target.requests)
    result = rig.execute()
    assert isinstance(result, VerificationFile)
    assert result.entries[0].level == "reproduced"
    assert len(rig.rig.target.requests) == before


def test_interrupcao_apos_primeira_resposta_preserva_controle_e_codigo(tmp_path: Path) -> None:
    from harness_dast.application.run_support import KillSwitchEngaged
    from harness_dast.domain.http_messages import HttpRequest, HttpResponse
    from tests.fakes.confirmation_rig import confirmation_target

    def handle(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        result = confirmation_target(request, jar)
        if request.operation_id.startswith("confirm:"):
            rig.switch.stopped = True
        return result

    rig = ConfirmationRig(tmp_path, handler=handle)
    with pytest.raises(KillSwitchEngaged):
        rig.execute()
    entry = rig.store.read().entries[0]
    assert entry.level == "inconclusive"
    assert entry.control is not None
    assert "HTTP 200" in entry.control
    assert entry.attack is not None
    assert "não realizado" in entry.attack


def test_scan_registra_recibo_do_alvo_entregue_ao_zap() -> None:
    from harness_dast.domain.scan_binding import bind_scan_seed
    from tests.fakes.scan_rig import ScanRig

    rig = ScanRig()
    rig.run_probe()
    result = rig.run_scan()
    assert result.entries
    for entry, started in zip(result.entries, rig.zap.started, strict=True):
        assert entry.seed_binding is not None
        expected = bind_scan_seed(
            entry.operation_id, started.method, started.url, entry.seed_binding.account
        )
        assert entry.seed_binding == expected


def test_sem_recibo_nao_abre_sessao(tmp_path: Path) -> None:
    rig = ConfirmationRig(tmp_path)
    scan = rig.rig.artifacts.scans[rig.run_id]
    entry = scan.entries[0].model_copy(update={"seed_binding": None})
    rig.rig.artifacts.scans[rig.run_id] = scan.model_copy(update={"entries": (entry,)})
    before = len(rig.rig.target.requests)
    result = rig.execute()
    assert isinstance(result, VerificationFile)
    assert result.entries[0].level == "not_verifiable"
    assert len(rig.rig.target.requests) == before


def test_ctrl_c_preserva_prova_parcial(tmp_path: Path) -> None:
    from harness_dast.domain.http_messages import HttpRequest, HttpResponse
    from tests.fakes.confirmation_rig import confirmation_target

    def handle(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id.startswith("confirm:"):
            raise KeyboardInterrupt
        return confirmation_target(request, jar)

    rig = ConfirmationRig(tmp_path, handler=handle)
    with pytest.raises(KeyboardInterrupt):
        rig.execute()
    entry = rig.store.read().entries[0]
    assert entry.level == "inconclusive"
    assert entry.attack is not None
    assert entry.control is not None


def test_escopo_recusado_preserva_erro_e_prova_antes_de_sessao(tmp_path: Path) -> None:
    from harness_dast.domain.scan_binding import bind_scan_seed

    rig = ConfirmationRig(tmp_path)
    log = rig.rig.store.exchanges[rig.run_id]
    exchange = log.exchanges[0].model_copy(update={"path": "/fora", "target": "/fora?q=ok"})
    rig.rig.store.exchanges[rig.run_id] = log.model_copy(update={"exchanges": (exchange,)})
    scan = rig.rig.artifacts.scans[rig.run_id]
    base = rig.rig.profiles.load("agenda").environment.base_url
    entry = scan.entries[0].model_copy(
        update={
            "path": "/fora",
            "seed_binding": bind_scan_seed("listar", "GET", base + "/fora?q=ok", "user_a"),
        }
    )
    rig.rig.artifacts.scans[rig.run_id] = scan.model_copy(update={"entries": (entry,)})
    report = rig.rig.artifacts.findings[rig.run_id]
    finding = report.findings[0].model_copy(update={"path_template": "/fora"})
    rig.rig.artifacts.findings[rig.run_id] = report.model_copy(update={"findings": (finding,)})
    before = len(rig.rig.target.requests)
    with pytest.raises(ScopeViolation) as error:
        rig.execute()
    assert error.value.exit_code == 3
    assert rig.store.read().entries[0].level == "inconclusive"
    assert len(rig.rig.target.requests) == before


def test_orcamento_inclui_login_e_receita(tmp_path: Path) -> None:
    from harness_dast.application.confirmation import ConfirmationRequest

    rig = ConfirmationRig(tmp_path)
    service = rig.service()
    before = len(rig.rig.target.requests)
    service.execute(ConfirmationRequest(product="agenda", run_id=rig.run_id))
    recipes, sessions = service.traffic
    assert sessions > 0
    assert recipes == 5
    assert recipes + sessions <= 12
    assert len(rig.rig.target.requests) - before == recipes + sessions


def test_revogacao_no_meio_preserva_codigo_e_resposta_parcial(tmp_path: Path) -> None:
    from harness_dast.application.confirmation import ConfirmationRequest
    from harness_dast.domain.errors import ScopeNotApproved
    from harness_dast.domain.http_messages import HttpRequest, HttpResponse
    from tests.fakes.confirmation_rig import RevocableProfiles, confirmation_target

    def handle(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        response = confirmation_target(request, jar)
        if request.operation_id.startswith("confirm:"):
            profiles.revoked = True
        return response

    rig = ConfirmationRig(tmp_path, handler=handle)
    profiles = RevocableProfiles(rig.rig.profiles)
    service = rig.service(profiles=profiles)
    with pytest.raises(ScopeNotApproved) as error:
        service.execute(ConfirmationRequest(product="agenda", run_id=rig.run_id))
    assert error.value.exit_code == 3
    entry = rig.store.read().entries[0]
    assert entry.level == "inconclusive"
    assert entry.control is not None
    assert "HTTP 200" in entry.control
    assert len([r for r in rig.rig.target.requests if r.operation_id.startswith("confirm:")]) == 1


def test_prazo_durante_receita_conserva_codigo_e_parcial(tmp_path: Path) -> None:
    from harness_dast.application.run_support import DeadlineReached
    from harness_dast.domain.http_messages import HttpRequest, HttpResponse
    from tests.fakes.confirmation_rig import confirmation_target

    def handle(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        response = confirmation_target(request, jar)
        if request.operation_id.startswith("confirm:"):
            rig.rig.clock.advance(86400)
        return response

    rig = ConfirmationRig(tmp_path, handler=handle)
    with pytest.raises(DeadlineReached) as error:
        rig.execute()
    assert error.value.exit_code == 3
    assert rig.store.read().entries[0].level == "inconclusive"


@pytest.mark.parametrize("error_kind", ["approval", "stale"])
def test_recusa_aprovacao_ou_pilha_antes_da_sessao(tmp_path: Path, error_kind: str) -> None:
    from harness_dast.application.common_ports import ReferencedFile
    from harness_dast.application.confirmation import ConfirmationRequest
    from harness_dast.domain.errors import ScopeNotApproved, StackStale
    from harness_dast.domain.profile import ProductProfile

    rig = ConfirmationRig(tmp_path)

    class RefusingProfiles:
        reads = 0

        def load(self, product: str) -> ProductProfile:
            self.reads += 1
            if self.reads > 1:
                if error_kind == "approval":
                    raise ScopeNotApproved("token-secreto")
                raise StackStale("token-secreto", stale_parts=("approval",))
            return rig.rig.profiles.load(product)

        def missing_files(
            self, product: str, profile: ProductProfile
        ) -> tuple[ReferencedFile, ...]:
            return rig.rig.profiles.missing_files(product, profile)

    before = len(rig.rig.target.requests)
    expected = ScopeNotApproved if error_kind == "approval" else StackStale
    with pytest.raises(expected) as error:
        rig.service(profiles=RefusingProfiles()).execute(
            ConfirmationRequest(product="agenda", run_id=rig.run_id)
        )
    assert "token-secreto" not in error.value.message
    assert rig.store.read().entries[0].level == "inconclusive"
    assert len(rig.rig.target.requests) == before
