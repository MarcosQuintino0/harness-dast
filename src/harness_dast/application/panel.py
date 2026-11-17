"""Caso de uso `panel`: gera as páginas HTML do painel da execução (ADR 0032).

Não toca rede nem ZAP: lê só arquivos da execução (`run.json`, `manifest.json`, `probe.json`,
`scan.json`, `findings.json`, `authz.json`, `metrics.json`), o perfil e o OpenAPI do produto,
monta a visão no domínio (`build_panel_view`) e grava as páginas em `runs/<run_id>/panel/`. Todo
arquivo é opcional: o que falta aparece no painel como "não medido", nunca como zero. Não confere
janela nem autorização: ler arquivos não envia nada ao alvo.

O painel é secundário. `refresh` (chamado pelo `report` e pelo `run`) NUNCA levanta erro do
harness: se não puder gerar, registra no log e devolve `None`. `execute` (o comando
`hdast panel`) levanta `ConfigError` para a pessoa corrigir.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import tzinfo
from typing import Protocol

import structlog

from harness_dast.application.common_ports import ProfileRepository, SpecLoader
from harness_dast.application.panel_ports import PanelFiles
from harness_dast.application.report_presentation import PresentationBuilder
from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.errors import ConfigError, HarnessError
from harness_dast.domain.panel.build import build_panel_view
from harness_dast.domain.panel.format import RunStateKind
from harness_dast.domain.panel.model import PANEL_DIR, PanelExplanation, PanelJournal
from harness_dast.domain.panel.pages import PAGES, render_panel
from harness_dast.domain.panel.sources import PanelSources
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.run_ref import require_run_id

ENTRY_PAGE = PAGES[0].file

_log = structlog.get_logger()


class PanelHooks(Protocol):
    """Ganchos opcionais que enriquecem o painel (diário de comandos e catálogo de explicação).

    A implementação real é `CatalogPanelHooks` (`application/panel_hooks.py`). Quem os entrega
    devolve modelos já prontos, e o painel funciona sem eles (a aba Terminal mostra o estado
    vazio e as falhas ficam sem a explicação do catálogo).
    """

    def commands(self, product: str, run_id: str) -> PanelJournal | None:
        """Comandos do agente nesta execução, ou `None` se não há diário deste teste."""
        ...

    def explanations(
        self, report: FindingsReport | None, authz: AuthzResult | None
    ) -> Mapping[str, PanelExplanation]:
        """Explicação simples por `finding_id` (vazio se o catálogo não conhece o tipo)."""
        ...


@dataclass(frozen=True)
class PanelRequest:
    """Pedido de um `panel`.

    Attributes:
        product: Produto.
        run_id: Execução; `None` usa a mais recente do produto.
    """

    product: str
    run_id: str | None = None


@dataclass(frozen=True)
class PanelOutcome:
    """Resultado de um `panel`.

    Attributes:
        product: Produto.
        run_id: Execução do painel.
        directory: Pasta das páginas, relativa à pasta da execução.
        entry: Página de entrada, relativa à pasta da execução.
        files: Páginas gravadas, relativas à pasta da execução.
        verdict: Como o teste terminou (`finished`, `partial` ou `error`).
        severe_findings: Falhas graves, ou `None` sem `findings.json`.
        sources: Arquivos da execução que existiam e foram lidos.
        missing: Arquivos que o painel conhece e não encontrou (aparecem como "não medido").
    """

    product: str
    run_id: str
    directory: str
    entry: str
    files: tuple[str, ...]
    verdict: RunStateKind
    severe_findings: int | None
    sources: tuple[str, ...]
    missing: tuple[str, ...]


class Panel:
    """Orquestra o `panel` (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        specs: SpecLoader,
        files: PanelFiles,
        timezone: tzinfo,
        hooks: PanelHooks | None = None,
        presentation: PresentationBuilder | None = None,
    ) -> None:
        """Cria o caso de uso com as portas de que precisa.

        Args:
            profiles: Perfis (dão o modo de caminho e a validade da carta).
            specs: Leitor do OpenAPI (dá o nome simples e a parte do sistema de cada função).
            files: Arquivos da execução que o painel lê e a gravação das páginas.
            timezone: Fuso das datas da página: o do computador que a gera.
            hooks: Diário de comandos e catálogo de explicação, quando existirem.
            presentation: Montagem opcional da visão consultiva de verificação.
        """
        self._profiles = profiles
        self._specs = specs
        self._files = files
        self._zone = timezone
        self._hooks = hooks
        self._presentation = presentation

    def execute(self, request: PanelRequest) -> PanelOutcome:
        """Gera as páginas do painel.

        Raises:
            ConfigError: Nenhuma execução do produto, execução sem nenhum arquivo conhecido,
                execução de outro produto, arquivo inválido ou falha de escrita.
        """
        run_id = self._resolve(request)
        profile = self._optional(run_id, "perfil", lambda _: self._profiles.load(request.product))
        found = self._read_all(request.product, run_id, profile)
        view = build_panel_view(found.sources)
        files = self._files.write_pages(run_id, render_panel(view))
        return PanelOutcome(
            product=request.product,
            run_id=run_id,
            directory=PANEL_DIR,
            entry=f"{PANEL_DIR}/{ENTRY_PAGE}",
            files=files,
            verdict=view.verdict.kind,
            severe_findings=view.verdict.severe_count,
            sources=found.present,
            missing=found.missing,
        )

    def refresh(self, product: str, run_id: str) -> str | None:
        """Gera o painel sem nunca derrubar quem chamou (`report` e `run`).

        Returns:
            A página de entrada, relativa à pasta da execução, ou `None` se não foi possível.
        """
        try:
            return self.execute(PanelRequest(product=product, run_id=run_id)).entry
        except HarnessError as error:
            _log.warning("panel_not_written", run_id=run_id, reason=error.message)
            return None

    def _resolve(self, request: PanelRequest) -> str:
        if request.run_id is not None:
            return require_run_id(request.run_id)
        latest = self._files.latest_run_id(request.product)
        if latest is None:
            raise ConfigError(
                "Não há nenhuma execução deste produto.",
                hint="Rode 'hdast run PRODUTO' (ou o probe e o scan) e tente de novo, ou informe "
                "--run com o run_id de uma execução existente (confira HDAST_RUNS_DIR).",
            )
        return latest

    def _read_all(self, product: str, run_id: str, profile: ProductProfile | None) -> "_Found":
        read = self._files
        summary = self._optional(run_id, "run.json", self._files.read_summary)
        manifest = self._optional(run_id, "manifest.json", read.read_manifest)
        probe = self._optional(run_id, "probe.json", read.read_probe)
        scan = self._optional(run_id, "scan.json", read.read_scan)
        findings = self._optional(run_id, "findings.json", read.read_findings)
        if findings is not None and findings.run_id != run_id:
            raise ConfigError(
                "O relatório pertence a outra execução.",
                hint="Confira o run_id e os arquivos da execução.",
            )
        authz = self._optional(run_id, "authz.json", read.read_authz)
        negative = self._optional(run_id, "negative.json", read.read_negative)
        metrics = self._optional(run_id, "metrics.json", self._files.read_metrics)
        agent_metrics = self._optional(run_id, "agent-metrics.json", read.read_agent_metrics)
        named = {
            "run.json": summary,
            "manifest.json": manifest,
            "probe.json": probe,
            "scan.json": scan,
            "findings.json": findings,
            "authz.json": authz,
            "negative.json": negative,
            "metrics.json": metrics,
        }
        present = tuple(name for name, item in named.items() if item is not None)
        _require_same_product(product, [item for item in named.values() if item is not None])
        authorization = profile.scope.authorization if profile else None
        journal = self._journal(product, run_id)
        sources = PanelSources(
            product=product,
            run_id=run_id,
            timezone=self._zone,
            summary=summary,
            manifest=manifest,
            probe=probe,
            scan=scan,
            findings=findings,
            authz=authz,
            negative=negative,
            metrics=metrics,
            agent_metrics=agent_metrics,
            operations=self._operations(product, run_id, profile),
            fence_mode=profile.scope.path_mode if profile else None,
            authorization_reference=authorization.reference if authorization else None,
            authorization_valid_until=authorization.valid_until if authorization else None,
            commands=journal.commands if journal else None,
            commands_skipped=journal.skipped_lines if journal else 0,
            explanations=self._hooks.explanations(findings, authz) if self._hooks else {},
            presentation=self._presentation.build(findings)
            if self._presentation and findings
            else None,
        )
        return _Found(sources, present, tuple(name for name in named if name not in present))

    def _journal(self, product: str, run_id: str) -> PanelJournal | None:
        """Diário do teste; ilegível ou ausente vira `None` (o painel mostra o estado vazio)."""
        if self._hooks is None:
            return None
        try:
            return self._hooks.commands(product, run_id)
        except HarnessError as error:
            _log.info(
                "panel_input_unavailable", run_id=run_id, file="journal", reason=error.message
            )
            return None

    def _operations(
        self, product: str, run_id: str, profile: ProductProfile | None
    ) -> tuple[Operation, ...]:
        if profile is None:
            return ()
        spec = self._optional(run_id, "openapi", lambda _: self._specs.load(product, profile))
        return spec.operations if spec else ()

    def _optional[T](self, run_id: str, name: str, read: Callable[[str], T | None]) -> T | None:
        """Lê um arquivo opcional; ausente ou ilegível vira `None` e fica no log."""
        try:
            return read(run_id)
        except HarnessError as error:
            _log.info("panel_input_unavailable", run_id=run_id, file=name, reason=error.message)
            return None


@dataclass(frozen=True)
class _Found:
    sources: PanelSources
    present: tuple[str, ...]
    missing: tuple[str, ...]


def _require_same_product(product: str, items: list[object]) -> None:
    if not items:
        raise ConfigError(
            "A execução não tem nenhum arquivo que o painel conheça.",
            hint="Confira o run_id e HDAST_RUNS_DIR; o painel precisa de ao menos um entre "
            "run.json, manifest.json, probe.json e scan.json.",
        )
    owners = {getattr(item, "product", product) for item in items}
    if owners != {product}:
        raise ConfigError(
            "A execução informada é de outro produto.",
            hint="Use o run_id de uma execução deste produto.",
        )
