"""Registro das páginas do painel: arquivo, rótulo da aba e função que desenha o miolo. Módulo puro.

Para acrescentar uma aba: crie o módulo `panel_NOME.py` com `render_NOME(view) -> str` (o
conteúdo do `<main>`, já escapado) e troque a função da linha correspondente em `PAGES`; a
casca, o menu e a gravação do arquivo vêm daqui. Os nomes dos arquivos são os do desenho
(`docs/design/execution-panel/screens/`) e os links do menu nunca quebram.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from harness_dast.domain.panel.authz import render_authz
from harness_dast.domain.panel.coverage import render_coverage
from harness_dast.domain.panel.findings import render_findings
from harness_dast.domain.panel.layout import TabItem, render_page
from harness_dast.domain.panel.model import PanelView
from harness_dast.domain.panel.stages import render_stages
from harness_dast.domain.panel.summary import render_summary
from harness_dast.domain.panel.terminal import render_terminal
from harness_dast.domain.panel.time import render_time

PageRenderer = Callable[[PanelView], str]
TabCounter = Callable[[PanelView], int | None]


@dataclass(frozen=True)
class PanelPage:
    """Uma página do painel.

    Attributes:
        file: Nome do arquivo gravado em `runs/<run_id>/panel/` (e do link do menu).
        label: Texto da aba.
        title: Título da página (`<title>`).
        render: Desenha o miolo (`<main>`) a partir da visão; devolve HTML já escapado.
        counter: Número que aparece ao lado da aba, ou `None` sem contador.
    """

    file: str
    label: str
    title: str
    render: PageRenderer
    counter: TabCounter | None = None


def severe_count(view: PanelView) -> int | None:
    """Contador da aba Falhas: as falhas graves (cinza se zero; `None` sem `findings.json`)."""
    return view.verdict.severe_count


PAGES: Final[tuple[PanelPage, ...]] = (
    PanelPage("summary.html", "Resumo", "Resumo do teste", render_summary),
    PanelPage("stages.html", "Etapas", "Etapas", render_stages),
    PanelPage("findings.html", "Falhas", "Falhas", render_findings, severe_count),
    PanelPage("coverage.html", "Cobertura", "Cobertura", render_coverage),
    PanelPage("authorization.html", "Autorização", "Autorização entre contas", render_authz),
    PanelPage("terminal.html", "Terminal", "Terminal", render_terminal),
    PanelPage("time-and-tokens.html", "Tempo e tokens", "Tempo e tokens", render_time),
)


def render_panel(view: PanelView) -> Mapping[str, str]:
    """Gera todas as páginas do teste: nome do arquivo -> HTML completo."""
    tabs = tuple(
        TabItem(page.file, page.label, page.counter(view) if page.counter else None)
        for page in PAGES
    )
    return {
        page.file: render_page(
            view, current=page.file, tabs=tabs, title=page.title, main=page.render(view)
        )
        for page in PAGES
    }
