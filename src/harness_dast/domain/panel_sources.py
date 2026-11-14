"""Entrada da montagem do painel: arquivos da execução (todos opcionais) e ganchos. Módulo puro."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, tzinfo

from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.panel_model import PanelCommand, PanelExplanation, PanelLinks
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.run_metrics import RunMetrics
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.scan_result import ScanResult


@dataclass(frozen=True)
class PanelSources:
    """Tudo que a montagem lê; cada campo opcional pode faltar.

    Attributes:
        product: Slug do produto.
        run_id: Pasta da execução.
        timezone: Fuso em que as datas do painel aparecem (o do computador que gera a página).
        summary: `run.json`.
        manifest: `manifest.json`.
        probe: `probe.json`.
        scan: `scan.json`.
        findings: `findings.json` (já traz a triagem mesclada).
        authz: `authz.json`.
        metrics: `metrics.json`.
        operations: Operações do OpenAPI, ou vazio se não foi possível ler o arquivo.
        fence_mode: Modo da cerca no perfil (só para mostrar), ou `None` sem perfil.
        authorization_reference: Referência da carta, ou `None`.
        authorization_valid_until: Último dia de validade da carta, ou `None`.
        commands: Gancho do diário de comandos, ou `None`.
        explanations: Gancho do catálogo de explicação, por `finding_id`.
        links: Destino dos dois primeiros pedaços do caminho.
    """

    product: str
    run_id: str
    timezone: tzinfo
    summary: RunSummary | None = None
    manifest: RunManifest | None = None
    probe: ProbeResult | None = None
    scan: ScanResult | None = None
    findings: FindingsReport | None = None
    authz: AuthzResult | None = None
    metrics: RunMetrics | None = None
    operations: Sequence[Operation] = ()
    fence_mode: str | None = None
    authorization_reference: str | None = None
    authorization_valid_until: date | None = None
    commands: tuple[PanelCommand, ...] | None = None
    explanations: Mapping[str, PanelExplanation] = field(default_factory=dict)
    links: PanelLinks = field(default_factory=PanelLinks)


def parse_moment(text: str | None, zone: tzinfo) -> datetime | None:
    """Lê um instante ISO 8601 (sem fuso conta como UTC) e o põe no fuso pedido."""
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(zone)
