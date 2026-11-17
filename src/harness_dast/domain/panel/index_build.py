"""Monta as linhas dos índices do painel e compara testes do mesmo tipo. Módulo puro.

A linha de uma execução sai do mesmo `PanelView` do painel (uma só fonte de verdade). A
comparação "o que mudou desde o anterior" usa o código curto da falha (`finding_id`), que vem
do fingerprint e não muda entre testes. "Não apareceu mais" NÃO é "corrigida": a função pode
não ter sido atacada desta vez (mesmo cuidado do `report --compare`).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from harness_dast.domain.panel.build import build_panel_view
from harness_dast.domain.panel.format import product_title
from harness_dast.domain.panel.index_model import (
    ProductEntry,
    ProductInfo,
    RowFinding,
    RunKind,
    RunRow,
)
from harness_dast.domain.panel.model import PanelView
from harness_dast.domain.panel.sources import PanelSources

_SCAN_KINDS: Final = ("scan",)
_LONGEST_OPEN: Final = 3
_MIN_STREAK: Final = 2
""""Há mais tempo" só faz sentido com dois testes seguidos."""


def _kind(view: PanelView) -> tuple[RunKind, str | None]:
    state = {item.key: item.state for item in view.stages}
    reached = {item.key for item in view.stages if not item.unreached}
    ran = {key for key, value in state.items() if value in ("done", "cut") and key in reached}
    if "scan" in ran and "authz" in ran:
        return "scan", "Varredura e teste entre contas"
    if "scan" in ran:
        return "scan", "Varredura completa" if state["scan"] == "done" else "Varredura"
    if "authz" in ran:
        return "authz", "Teste entre contas"
    if "probe" in ran:
        return "probe", "Só alcance"
    if "preflight" in ran:
        return "preflight", "Só conferência"
    return "none", None


def row_from_view(view: PanelView, *, incomplete: bool, panel_link: str | None) -> RunRow:
    """Linha de uma execução legível (`incomplete` marca arquivo que não pôde ser lido)."""
    kind, what = _kind(view)
    verdict = view.verdict
    basis = verdict.functions_planned or verdict.functions_attempted
    if basis is None:
        basis = verdict.functions_total
    return RunRow(
        run_id=view.identity.run_id,
        product=view.identity.product,
        state="partial" if incomplete else "ok",
        started_at=view.identity.started_at,
        kind=kind,
        what_ran=what,
        verdict=verdict.kind,
        functions_attacked=verdict.functions_attacked,
        functions_basis=basis,
        functions_total=verdict.functions_total,
        severe_count=verdict.severe_count,
        severe=tuple(
            RowFinding(finding_id=item.finding_id, title=item.function_name or item.title)
            for item in view.severe
        ),
        duration_seconds=view.identity.duration_seconds,
        tokens=view.measurements.tokens_total,
        fence_mode=view.identity.fence_mode,
        panel_link=panel_link,
    )


def row_from_sources(src: PanelSources, *, incomplete: bool, panel_link: str | None) -> RunRow:
    """Monta a visão da execução e a resume numa linha."""
    return row_from_view(build_panel_view(src), incomplete=incomplete, panel_link=panel_link)


def empty_row(
    run_id: str, product: str, started_at: datetime | None, panel_link: str | None
) -> RunRow:
    """Linha "sem dados": a execução existe, mas nenhum arquivo dela pôde ser lido."""
    return RunRow(
        run_id=run_id,
        product=product,
        state="empty",
        started_at=started_at,
        panel_link=panel_link,
    )


def make_entry(product: str, info: ProductInfo, rows: Sequence[RunRow]) -> ProductEntry:
    """Produto com as execuções da mais recente para a mais antiga (pelo `run_id`)."""
    ordered = tuple(sorted(rows, key=lambda item: item.run_id, reverse=True))
    return ProductEntry(product=product, name=product_title(product), info=info, rows=ordered)


@dataclass(frozen=True)
class Change:
    """O que mudou entre dois testes do mesmo tipo.

    Attributes:
        new: Falhas que não estavam no teste anterior.
        persistent: Falhas que continuam.
        gone: Falhas do teste anterior que não apareceram desta vez.
        new_items: Títulos das novas.
        persistent_items: Títulos das que continuam.
        gone_items: Títulos das que não apareceram.
    """

    new: int
    persistent: int
    gone: int
    new_items: tuple[str, ...]
    persistent_items: tuple[str, ...]
    gone_items: tuple[str, ...]


def latest_report(rows: Sequence[RunRow]) -> RunRow | None:
    """Teste mais recente que tem relatório de falhas (as falhas "abertas" vêm dele).

    Um teste mais novo sem relatório (por exemplo, um erro na conferência) não apaga as
    falhas conhecidas do último relatório.
    """
    return next((row for row in rows if comparable(row)), None)


def comparable(row: RunRow) -> bool:
    """Se a linha entra na comparação: tem relatório de falhas e rodou alguma etapa."""
    return row.state != "empty" and row.severe_count is not None and row.kind != "none"


def previous_of(rows: Sequence[RunRow], index: int) -> RunRow | None:
    """Teste anterior do mesmo tipo (`rows` da mais recente para a mais antiga)."""
    current = rows[index]
    for older in rows[index + 1 :]:
        if older.state != "empty" and older.kind == current.kind:
            return older
    return None


def diff(previous: RunRow, current: RunRow) -> Change | None:
    """Compara as falhas graves; `None` quando um dos dois testes não tem relatório."""
    if not (comparable(previous) and comparable(current)):
        return None
    before = {item.finding_id: item.title for item in previous.severe}
    now = {item.finding_id: item.title for item in current.severe}
    new = [now[key] for key in now if key not in before]
    persistent = [now[key] for key in now if key in before]
    gone = [before[key] for key in before if key not in now]
    return Change(
        new=len(new),
        persistent=len(persistent),
        gone=len(gone),
        new_items=tuple(new),
        persistent_items=tuple(persistent),
        gone_items=tuple(gone),
    )


@dataclass(frozen=True)
class OpenFinding:
    """Falha aberta e há quantos testes seguidos ela aparece.

    Attributes:
        title: Título.
        since: Início do teste mais antigo da sequência.
        tests: Quantos testes seguidos do mesmo tipo a mostram.
    """

    title: str
    since: datetime | None
    tests: int


def longest_open(rows: Sequence[RunRow]) -> tuple[OpenFinding, ...]:
    """Falhas do teste mais recente que já apareciam nos anteriores (as mais antigas primeiro).

    Só entram as que aparecem em dois ou mais testes seguidos do mesmo tipo.
    """
    if not rows or not comparable(rows[0]):
        return ()
    same = [row for row in rows if row.kind == rows[0].kind and comparable(row)]
    found: list[OpenFinding] = []
    for item in same[0].severe:
        streak = 0
        since = same[0].started_at
        for row in same:
            if item.finding_id not in {entry.finding_id for entry in row.severe}:
                break
            streak += 1
            since = row.started_at
        if streak >= _MIN_STREAK:
            found.append(OpenFinding(title=item.title, since=since, tests=streak))
    found.sort(key=lambda item: item.tests, reverse=True)
    return tuple(found[:_LONGEST_OPEN])


def is_sweep(row: RunRow) -> bool:
    """Se a linha é uma varredura COMPLETA com relatório (entra no gráfico de falhas graves).

    Varredura que parou no meio vê só parte das funções: ela não é comparável com as completas.
    """
    return (
        row.kind in _SCAN_KINDS
        and row.severe_count is not None
        and row.state != "empty"
        and row.verdict == "finished"
    )
