"""Índices do painel: `runs/index.html` (produtos) e `runs/history-<produto>.html` (histórico).

Lê só arquivos das pastas de execução e os perfis (para a validade da carta); não usa rede nem o
ZAP. Execução ilegível ou de versão antiga entra no índice como linha "sem dados" (ou "dados
incompletos"): nunca some e nunca derruba o índice. `IndexedPanel` envolve o `Panel` e refaz os
índices sempre que um painel é gerado; `rebuild` é o modo explícito (`hdast panel --index`).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, tzinfo
from typing import Protocol

import structlog

from harness_dast.application.panel import PanelOutcome, PanelRequest
from harness_dast.application.panel_index_ports import PanelIndexFiles, RunFolder
from harness_dast.application.ports import Clock, PanelFiles, ProfileRepository
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.panel_index_build import empty_row, make_entry, row_from_sources
from harness_dast.domain.panel_index_model import ProductEntry, ProductInfo, RunRow
from harness_dast.domain.panel_index_pages import render_history, render_products
from harness_dast.domain.panel_model import INDEX_FILE, history_file
from harness_dast.domain.panel_sources import PanelSources

_log = structlog.get_logger()


class PanelGenerator(Protocol):
    """O `Panel` visto por quem o envolve."""

    def execute(self, request: PanelRequest) -> PanelOutcome:
        """Gera as páginas de um teste."""
        ...

    def refresh(self, product: str, run_id: str) -> str | None:
        """Gera sem nunca derrubar quem chamou."""
        ...


@dataclass(frozen=True)
class IndexedOutcome:
    """Resultado de `hdast panel`: o painel do teste e os índices refeitos.

    Attributes:
        panel: Resultado do painel do teste, ou `None` no modo só dos índices.
        indexes: Índices gravados (nomes de arquivo em `runs/`).
    """

    panel: PanelOutcome | None
    indexes: tuple[str, ...]


def _stamp_moment(run_id: str, zone: tzinfo) -> datetime | None:
    try:
        stamp = datetime.strptime(run_id[:20], "%Y-%m-%dT%H-%M-%SZ")
    except ValueError:
        return None
    return stamp.replace(tzinfo=UTC).astimezone(zone)


class _Reads:
    """Lê os arquivos de uma execução contando os que existem e os que não puderam ser lidos."""

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self.found = 0
        self.failed = 0

    def get[T](self, name: str, read: Callable[[str], T | None]) -> T | None:
        try:
            item = read(self._run_id)
        except HarnessError as error:
            self.failed += 1
            _log.info(
                "panel_index_input_unavailable",
                run_id=self._run_id,
                file=name,
                reason=error.message,
            )
            return None
        self.found += item is not None
        return item


class PanelIndexer:
    """Monta e grava os índices a partir das pastas de execução."""

    def __init__(
        self,
        *,
        files: PanelFiles,
        index_files: PanelIndexFiles,
        profiles: ProfileRepository,
        clock: Clock,
        timezone: tzinfo,
    ) -> None:
        """Cria o gerador de índices.

        Args:
            files: Leitura dos arquivos de cada execução.
            index_files: Lista das pastas de execução e gravação dos índices.
            profiles: Perfis (validade da carta e modo da cerca).
            clock: Relógio (a data de hoje decide "carta vence em 3 dias").
            timezone: Fuso das datas: o do computador que gera as páginas.
        """
        self._files = files
        self._index_files = index_files
        self._profiles = profiles
        self._clock = clock
        self._zone = timezone

    def rebuild(self) -> tuple[str, ...]:
        """Refaz o índice de produtos e o histórico de cada produto.

        Returns:
            Os arquivos gravados, em `runs/`.

        Raises:
            ConfigError: Falha de escrita dos índices. Execução ilegível NÃO é erro.
        """
        folders = self._index_files.list_runs()
        absorbed = self._absorbed(folders)
        by_product: dict[str, list[RunRow]] = {}
        for folder in folders:
            if folder.run_id not in absorbed:
                by_product.setdefault(folder.product, []).append(self._row(folder))
        entries = [
            make_entry(product, self._info(product), rows)
            for product, rows in sorted(by_product.items())
        ]
        today = self._clock.now().astimezone(self._zone).date()
        written = [self._index_files.write_index(INDEX_FILE, render_products(entries, today))]
        written += [self._write_history(entry, today) for entry in entries]
        return tuple(written)

    def _absorbed(self, folders: Sequence[RunFolder]) -> frozenset[str]:
        """Pastas que um `run.json` cita como etapa de outra pasta (a conferência do `run`).

        O `run` faz o preflight numa pasta própria e a execução de verdade começa no `probe`, em
        outra: a primeira não é um teste à parte, é a conferência da segunda.
        """
        cited: set[str] = set()
        for folder in folders:
            try:
                summary = self._files.read_summary(folder.run_id)
            except HarnessError:
                continue
            if summary is not None:
                cited.update(
                    stage.run_id
                    for stage in summary.stages
                    if stage.run_id is not None and stage.run_id != summary.run_id
                )
        return frozenset(cited)

    def _write_history(self, entry: ProductEntry, today: date) -> str:
        name = history_file(entry.product)
        return self._index_files.write_index(name, render_history(entry, today))

    def _row(self, folder: RunFolder) -> RunRow:
        run_id = folder.run_id
        link = f"{run_id}/panel/summary.html" if self._index_files.has_panel(run_id) else None
        reads = _Reads(run_id)
        files = self._files
        sources = PanelSources(
            product=folder.product,
            run_id=run_id,
            timezone=self._zone,
            summary=reads.get("run.json", files.read_summary),
            manifest=reads.get("manifest.json", files.read_manifest),
            probe=reads.get("probe.json", files.read_probe),
            scan=reads.get("scan.json", files.read_scan),
            findings=reads.get("findings.json", files.read_findings),
            authz=reads.get("authz.json", files.read_authz),
            negative=reads.get("negative.json", files.read_negative),
            metrics=reads.get("metrics.json", files.read_metrics),
        )
        started = _stamp_moment(run_id, self._zone)
        if reads.found == 0:
            return empty_row(run_id, folder.product, started, link)
        try:
            return row_from_sources(sources, incomplete=reads.failed > 0, panel_link=link)
        except HarnessError as error:
            _log.info("panel_index_row_failed", run_id=run_id, reason=error.message)
            return empty_row(run_id, folder.product, started, link)

    def _info(self, product: str) -> ProductInfo:
        try:
            profile = self._profiles.load(product)
        except HarnessError as error:
            _log.info("panel_index_profile_unavailable", product=product, reason=error.message)
            return ProductInfo()
        authorization = profile.scope.authorization
        return ProductInfo(
            profile_available=True,
            authorization_reference=authorization.reference if authorization else None,
            valid_until=authorization.valid_until if authorization else None,
            fence_mode=profile.scope.path_mode,
        )


class IndexedPanel:
    """O painel de um teste mais os índices: refaz os índices sempre que gera um painel."""

    def __init__(self, panel: PanelGenerator, indexer: PanelIndexer) -> None:
        """Cria o envoltório.

        Args:
            panel: O `Panel` do teste.
            indexer: O gerador dos índices.
        """
        self._panel = panel
        self._indexer = indexer

    def execute(self, request: PanelRequest) -> IndexedOutcome:
        """Gera o painel do teste e refaz os índices.

        Raises:
            ConfigError: As do `Panel` e a falha de escrita dos índices.
        """
        outcome = self._panel.execute(request)
        return IndexedOutcome(panel=outcome, indexes=self._indexer.rebuild())

    def rebuild_indexes(self) -> IndexedOutcome:
        """Só refaz os índices (`hdast panel --index`)."""
        return IndexedOutcome(panel=None, indexes=self._indexer.rebuild())

    def refresh(self, product: str, run_id: str) -> str | None:
        """Gera o painel e os índices sem nunca derrubar quem chamou (`report` e `run`)."""
        entry = self._panel.refresh(product, run_id)
        try:
            self._indexer.rebuild()
        except HarnessError as error:
            _log.warning("panel_index_not_written", run_id=run_id, reason=error.message)
        return entry
