"""Página "Ao vivo" do painel (ADR 0034): a CLI regrava `panel/live.html` durante o `hdast run`.

O `run` avisa a cada mudança de etapa e a varredura avisa a cada função; nada aqui cria laço de
tempo, thread ou espera. A página se recarrega sozinha (`<meta http-equiv="refresh">`, sem
JavaScript). Quando o `run` acaba, a página é regravada uma última vez, sem a recarga, ligando
para o Resumo e as Etapas.

Garantia: nenhum método levanta erro do harness. Falha ao montar ou gravar a página vai para o
log (`panel_live_not_written`) e o `run` segue como se nada tivesse acontecido. A página só
existe depois do `preflight`: antes dele ainda não há pasta de execução.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, tzinfo

import structlog

from harness_dast.application.common_ports import Clock, KillSwitch, ProfileRepository, SpecLoader
from harness_dast.application.panel_index import PanelIndexer
from harness_dast.application.panel_ports import PanelFiles
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.panel.build_content import function_names
from harness_dast.domain.panel.build_stages import STAGE_LABELS
from harness_dast.domain.panel.format import RunStateKind, product_title
from harness_dast.domain.panel.live import LIVE_FILE, render_live
from harness_dast.domain.panel.live_model import LivePhase, LiveStage, LiveStageState, LiveView
from harness_dast.domain.panel.model import PanelLinks, panel_links
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run_summary import STAGES, RunSummary, StageName, StageRecord
from harness_dast.domain.traffic import TrafficSummary

_log = structlog.get_logger()
_RECORD_STATE: dict[str, LiveStageState] = {
    "ok": "done",
    "failed": "cut",
    "interrupted": "cut",
    "skipped": "skipped",
}


@dataclass
class _State:
    """O que a página já sabe (por instância: um `run` por vez, sem estado de módulo)."""

    product: str
    run_id: str
    started: datetime
    authz: bool
    negative: bool
    stage: StageName = "preflight"
    stage_began: datetime | None = None
    records: tuple[StageRecord, ...] = ()
    scan_done: int | None = None
    scan_total: int | None = None
    current_operation: str | None = None
    traffic: TrafficSummary | None = None
    tried: int | None = None
    reached: int | None = None
    links: PanelLinks = field(default_factory=PanelLinks)


class LiveBoard:
    """Regrava `live.html` a cada mudança de etapa e a cada função varrida."""

    def __init__(
        self,
        *,
        files: PanelFiles,
        profiles: ProfileRepository,
        specs: SpecLoader,
        clock: Clock,
        timezone: tzinfo,
        kill_switch: KillSwitch,
        indexer: PanelIndexer | None = None,
    ) -> None:
        """Cria a página ao vivo.

        Args:
            files: Leitura do `probe.json` e gravação da página.
            profiles: Perfis (prazo e modo da cerca).
            specs: Leitor do OpenAPI (nome simples da função em ataque).
            clock: Relógio injetado.
            timezone: Fuso das horas da página.
            kill_switch: Trava de emergência (a página diz "parando" quando acionada).
            indexer: Índices; refeitos uma vez, na primeira gravação, para os links do caminho
                existirem. `None` deixa o caminho do alto como texto.
        """
        self._files = files
        self._profiles = profiles
        self._specs = specs
        self._clock = clock
        self._zone = timezone
        self._kill = kill_switch
        self._indexer = indexer
        self._state: _State | None = None
        self._names: dict[str, str] | None = None

    def stage_started(
        self,
        product: str,
        run_id: str,
        stage: StageName,
        records: Sequence[StageRecord],
        *,
        started: datetime,
        authz: bool,
        negative: bool = True,
    ) -> None:
        """A etapa começou: regrava a página (a partir do `probe`, quando a pasta já existe)."""
        now = self._clock.now()
        state = self._state
        if state is None or state.run_id != run_id:
            state = _State(
                product=product, run_id=run_id, started=started, authz=authz, negative=negative
            )
            state.links = self._first_links(product)
            self._state = state
        state.stage, state.stage_began, state.records = stage, now, tuple(records)
        if stage in ("scan", "authz", "negative", "report"):
            self._read_probe(state)
        self._write(state, "running")

    def scan_progress(
        self,
        run_id: str,
        done: int,
        total: int,
        operation_id: str | None,
        traffic: TrafficSummary | None,
    ) -> None:
        """Uma função da varredura começou ou acabou: regrava a página."""
        state = self._state
        if state is None or state.run_id != run_id:
            return
        state.scan_done, state.scan_total = done, total
        state.current_operation = operation_id
        state.traffic = traffic
        self._write(state, "running")

    def run_finished(self, product: str, run_id: str, summary: RunSummary) -> None:
        """O `run` acabou: última gravação, sem recarga, com o link do Resumo e das Etapas."""
        state = self._state
        if state is None or state.run_id != run_id:
            return
        state.records = summary.stages
        self._write(state, "finished", summary=summary)
        self._state = None

    def _first_links(self, product: str) -> PanelLinks:
        """Os índices só são refeitos uma vez; sem eles, o caminho fica como texto."""
        if self._indexer is None:
            return PanelLinks()
        try:
            self._indexer.rebuild()
        except HarnessError as error:
            _log.warning("panel_live_index_failed", reason=error.message)
            return PanelLinks()
        return panel_links(product)

    def _read_probe(self, state: _State) -> None:
        if state.tried is not None:
            return
        try:
            probe = self._files.read_probe(state.run_id)
        except HarnessError as error:
            _log.info("panel_live_probe_unavailable", reason=error.message)
            return
        if probe is not None and not probe.dry_run:
            state.tried = probe.summary.operations_sent
            state.reached = probe.summary.successes + probe.summary.by_outcome.get(
                "auth_rejected_expected", 0
            )

    def _write(self, state: _State, phase: LivePhase, *, summary: RunSummary | None = None) -> None:
        try:
            view = self._view(state, phase, summary)
            self._files.write_pages(state.run_id, {LIVE_FILE: render_live(view)})
        except HarnessError as error:
            _log.warning("panel_live_not_written", run_id=state.run_id, reason=error.message)

    def _view(self, state: _State, phase: LivePhase, summary: RunSummary | None) -> LiveView:
        now = self._clock.now()
        engaged = phase == "running" and self._kill.engaged()
        profile = self._profile(state.product)
        outcome, reason = _outcome(summary)
        traffic = state.traffic if state.traffic and state.traffic.enabled else None
        return LiveView(
            product=state.product,
            product_name=product_title(state.product),
            run_id=state.run_id,
            phase="stopping" if engaged else phase,
            outcome=outcome,
            reason=reason,
            started_at=state.started.astimezone(self._zone),
            updated_at=now.astimezone(self._zone),
            elapsed_seconds=max((now - state.started).total_seconds(), 0.0),
            limit_minutes=profile.limits.max_duration_minutes if profile else None,
            fence_mode=profile.scope.path_mode if profile else None,
            stages=self._stages(state, phase, now),
            functions_tried=state.tried,
            functions_reached=state.reached,
            scan_done=state.scan_done,
            scan_total=state.scan_total,
            current_function=self._function_name(state),
            allowed=traffic.allowed if traffic else None,
            denied=traffic.denied if traffic else None,
            outside_allow=traffic.allowed_outside_allow if traffic else None,
            links=state.links,
        )

    def _profile(self, product: str) -> ProductProfile | None:
        try:
            return self._profiles.load(product)
        except HarnessError as error:
            _log.info("panel_live_profile_unavailable", reason=error.message)
            return None

    def _function_name(self, state: _State) -> str | None:
        operation = state.current_operation
        if operation is None:
            return None
        if self._names is None:
            self._names = {}
            profile = self._profile(state.product)
            if profile is not None:
                try:
                    self._names = function_names(
                        self._specs.load(state.product, profile).operations
                    )
                except HarnessError as error:
                    _log.info("panel_live_spec_unavailable", reason=error.message)
        return self._names.get(operation, operation)

    def _stages(self, state: _State, phase: LivePhase, now: datetime) -> tuple[LiveStage, ...]:
        records = {item.name: item for item in state.records}
        built: list[LiveStage] = []
        for key in STAGES:
            if (key == "authz" and not state.authz) or (key == "negative" and not state.negative):
                continue
            record = records.get(key)
            status: LiveStageState = (
                _RECORD_STATE.get(record.status, "pending") if record else "pending"
            )
            seconds = record.duration_seconds if record and status != "pending" else None
            if phase != "finished" and key == state.stage:
                status = "running"
                seconds = (now - state.stage_began).total_seconds() if state.stage_began else None
            built.append(LiveStage(key=key, label=STAGE_LABELS[key], state=status, seconds=seconds))
        return tuple(built)


def _outcome(summary: RunSummary | None) -> tuple[RunStateKind | None, str | None]:
    if summary is None:
        return None, None
    reason = next(
        (
            item.message
            for item in summary.stages
            if item.status in ("failed", "interrupted") and item.message
        ),
        None,
    )
    if summary.status in ("completed", "findings"):
        return "finished", None
    if not summary.stages:
        return "partial", reason
    first = summary.stages[0]
    return ("error" if first.status in ("failed", "interrupted") else "partial"), reason
