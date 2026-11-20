"""Cenário de confirmação com cliente falso e armazenamento real temporário."""

from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from harness_dast.adapters.storage.verification_store import VerificationStore
from harness_dast.application.account_session import TokenCache
from harness_dast.application.common_ports import ProfileRepository, ReferencedFile
from harness_dast.application.confirmation import (
    Confirmation,
    ConfirmationDependencies,
    ConfirmationRequest,
)
from harness_dast.application.confirmation_ports import NucleiReproducer
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.probe_exchange import ExchangeLog, ExchangeRecord
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.scan_binding import bind_scan_seed
from harness_dast.domain.scan_result import ScanEntry
from tests.fakes.rig import default_handler
from tests.fakes.scan_rig import ScanRig


class ConfirmationSwitch:
    """Trava programável sem relógio ou rede."""

    def __init__(self, stopped: bool = False) -> None:
        self.stopped = stopped

    def engaged(self) -> bool:
        return self.stopped


class StaleProfiles:
    """Permite a primeira leitura e simula pilha desatualizada antes do envio."""

    def __init__(self, source: ProfileRepository) -> None:
        self._source = source
        self._reads = 0

    def load(self, product: str) -> ProductProfile:
        """Falha fechada na revalidação após o planejamento."""
        self._reads += 1
        if self._reads > 1:
            raise ConfigError("Pilha desatualizada.")
        return self._source.load(product)

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Delega a inspeção de arquivos do perfil."""
        return self._source.missing_files(product, profile)


def confirmation_target(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
    """Comporta-se como alvo sintético e diferencia o controle booleano falso."""
    if request.operation_id.startswith("confirm:"):
        value = parse_qs(urlsplit(request.url).query).get("q", [""])[0]
        return HttpResponse(status=200, body=b"false" if value.endswith("'2") else b"true")
    result = default_handler(request, jar)
    assert isinstance(result, HttpResponse)
    return result


class ConfirmationRig:
    """Cria probe e scan em memória, com resultado de verificação gravado em tmp_path."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        stopped: bool = False,
        plugin: str = "40018",
        handler: Callable[[HttpRequest, dict[str, str]], HttpResponse] = confirmation_target,
        profile: ProductProfile | None = None,
    ) -> None:
        self.rig = ScanRig(handler=handler, profile=profile)
        probe = self.rig.run_probe()
        scan = self.rig.run_scan()
        self.run_id = probe.run_id
        entry = ScanEntry(
            operation_id="listar",
            method="GET",
            path="/api/pacientes",
            message_id=1,
            scan_id="1",
            outcome="completed",
            requests=1,
            seed_binding=bind_scan_seed(
                "listar",
                "GET",
                self.rig.profiles.load("agenda").environment.base_url + "/api/pacientes?q=normal",
                "user_a",
            ),
        )
        self.rig.artifacts.scans[self.run_id] = scan.model_copy(update={"entries": (entry,)})
        exchange = ExchangeRecord(
            operation_id="listar",
            method="GET",
            path="/api/pacientes",
            target="/api/pacientes?q=normal",
            account="user_a",
            status=200,
        )
        self.rig.store.exchanges[self.run_id] = ExchangeLog(
            run_id=self.run_id, product="agenda", exchanges=(exchange,)
        )
        source = Path("tests/fixtures/zap_alerts/findings.golden.json").read_text(encoding="utf-8")
        report = FindingsReport.model_validate_json(source)
        finding = report.findings[0].model_copy(
            update={
                "fingerprint": "a" * 64,
                "plugin_id": plugin,
                "method": "GET",
                "operation_id": "listar",
                "path_template": "/api/pacientes",
                "parameter": "q",
                "input_vector": "querystring",
                "seed_outcome": None,
            }
        )
        self.rig.artifacts.findings[self.run_id] = report.model_copy(
            update={
                "run_id": self.run_id,
                "product": "agenda",
                "findings": (finding,),
                "authz": None,
            }
        )
        self.path = tmp_path / "verification.json"
        self.switch = ConfirmationSwitch(stopped)
        self.store = VerificationStore(self.path, self.rig.vault.mask)

    def execute(
        self,
        *,
        maximum: int = 30,
        finding: str | None = None,
        nuclei: NucleiReproducer | None = None,
    ) -> object:
        """Executa usando adaptadores falsos de rede e o armazém real."""
        return self.service(nuclei=nuclei).execute(
            ConfirmationRequest(
                product="agenda", run_id=self.run_id, maximum=maximum, finding=finding
            )
        )

    def service(
        self, profiles: ProfileRepository | None = None, nuclei: NucleiReproducer | None = None
    ) -> Confirmation:
        """Monta o serviço real com portas falsas e arquivo temporário."""
        deps = ConfirmationDependencies(
            profiles=profiles or self.rig.profiles,
            artifacts=self.rig.artifacts,
            verification=self.store,
            existing=self.path.exists(),
            store=self.rig.store,
            client=self.rig.target,
            secrets=self.rig.secrets,
            vault=self.rig.vault,
            clock=self.rig.clock,
            sleeper=self.rig.clock,
            kill_switch=self.switch,
            token_cache=TokenCache(),
            marker=lambda: "0123456789abcdef",
            nuclei=nuclei,
        )
        return Confirmation(deps)


def recipe_target(mode: str) -> Callable[[HttpRequest, dict[str, str]], HttpResponse]:
    """Simula efeito repetível de cada receita, mantendo login do cenário padrão."""

    def handle(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if not request.operation_id.startswith("confirm:"):
            result = default_handler(request, jar)
            assert isinstance(result, HttpResponse)
            return result
        value = parse_qs(urlsplit(request.url).query).get("q", [""])[0]
        if mode == "time":
            return HttpResponse(
                status=200, body=b"ok", elapsed_ms=2100 if "pg_sleep" in value else 20
            )
        if mode == "xss":
            return HttpResponse(status=200, content_type="text/html", body=value.encode())
        if mode == "error" and value == "'":
            return HttpResponse(
                status=500, body=b"Traceback (most recent call last): synthetic error"
            )
        return HttpResponse(status=200, body=b"ok")

    return handle


class RevocableProfiles:
    """Dublê que permite revogar a aprovação antes ou durante a confirmação."""

    def __init__(self, source: ProfileRepository) -> None:
        self.source = source
        self.revoked = False

    def load(self, product: str) -> ProductProfile:
        """Recusa sem tráfego quando uma pessoa revogou a aprovação."""
        if self.revoked:
            from harness_dast.domain.errors import ScopeNotApproved

            raise ScopeNotApproved("Aprovação revogada.")
        return self.source.load(product)

    def missing_files(self, product: str, profile: ProductProfile) -> tuple[ReferencedFile, ...]:
        """Delega a inspeção ao falso de perfil."""
        return self.source.missing_files(product, profile)
