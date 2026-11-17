"""Casca das páginas do painel e os componentes que todas as abas dividem. Módulo puro.

A casca é a mesma em toda página: `lang="pt-BR"`, política de conteúdo (CSP) que proíbe script e
qualquer recurso de fora, o caminho `hdast / Produto / data · hora`, o menu de abas com
`aria-current="page"` e o rodapé. Os componentes (painel, etiqueta, marcador de estado, medidor,
número em destaque, barra com `role="img"`, bloco de terminal) escrevem o HTML do desenho
(`docs/design/execution-panel/system/components*.html`).

Segurança: todo texto que vem do alvo, do OpenAPI, do ZAP, do agente ou de arquivo entra por
`html_safe` (`h.text`, `h.ident`, `h.block`); texto nosso entra por `h.plain`. Nenhum componente
recebe HTML já pronto de fora desta família: quem chama passa texto e o componente o escapa, ou
passa o HTML que outro componente devolveu. Sem JavaScript, sem recurso externo.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel.format import CONFIDENCE_WORDS, fmt_datetime, fmt_duration
from harness_dast.domain.panel.model import PanelLinks, PanelView
from harness_dast.domain.panel.style import STYLE

CSP: Final = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; "
    "form-action 'none'"
)
Tone = Literal["run", "ok", "gr", "am", "mu"]
MarkerKind = Literal["ok", "gr", "am", "run", "no", "out"]

_SPOKEN: Final[dict[str, str]] = {
    "ok": "ok: ",
    "gr": "grave: ",
    "am": "atenção: ",
    "run": "agora: ",
    "no": "",
    "out": "proibido: ",
}
_MODE_WORDS: Final[dict[str, str]] = {"strict": "modo estrito", "wide": "modo amplo"}
STATE_CHIP: Final[dict[str, tuple[Tone, str]]] = {
    "finished": ("ok", "Terminado"),
    "partial": ("am", "Parou no meio"),
    "error": ("gr", "Erro"),
}
_FOOTER: Final = (
    "Painel local gerado pelo hdast, sem internet e sem script. Pode conter prova de falhas "
    "(pedidos e respostas do ambiente de teste, com dados inventados, segundo a carta): "
    "compartilhe só com quem pode ver."
)


@dataclass(frozen=True)
class TabItem:
    """Uma aba do menu.

    Attributes:
        file: Nome do arquivo da página (link relativo).
        label: Texto da aba.
        count: Contador ao lado do texto (vermelho se maior que zero, cinza se zero), ou `None`.
        enabled: `False` para a aba cuja página ainda não existe (durante o teste ao vivo): sai
            como texto apagado, nunca como link quebrado.
    """

    file: str
    label: str
    count: int | None = None
    enabled: bool = True


# ---------------------------------------------------------------- componentes


def chip(text: str, tone: Tone, *, dot: bool = True, raw: bool = False) -> str:
    """Etiqueta (estado ou informação neutra). `raw=True` só para texto nosso já escapado."""
    inner = text if raw else h.plain(text)
    return f'<span class="chip ch-{tone}">{"<i></i>" if dot else ""}{inner}</span>'


def marker(kind: MarkerKind) -> str:
    """Marcador de estado: forma própria por estado, mais o texto para leitor de tela."""
    spoken = f'<span class="vh">{_SPOKEN[kind]}</span>' if _SPOKEN[kind] else ""
    return f'<i class="dotk k-{kind}"></i>{spoken}'


def meter(level: int) -> str:
    """Medidor de confiança em três degraus (não é nota), sempre com a palavra ao lado."""
    word = CONFIDENCE_WORDS[max(0, min(level, 3) - 1)]
    filled = "".join(f'<i class="{"f" if n < level else ""}"></i>' for n in range(3))
    label = h.plain(f"{word}: degrau {level} de 3")
    return f'<span class="bars" role="img" aria-label="{label}">{filled}</span> {h.plain(word)}'


def stat(value: str, caption: str, *, tone: Tone | None = None) -> str:
    """Número em destaque com a legenda. Cor só quando o número é um estado."""
    style = f' style="color: var(--{tone})"' if tone else ""
    return f'<div class="stat"><b{style}>{h.plain(value)}</b><span>{h.plain(caption)}</span></div>'


def card(inner: str, *, style: str = "", extra_class: str = "") -> str:
    """Painel (card). Painel não vai dentro de painel."""
    attrs = f' style="{h.plain(style)}"' if style else ""
    cls = f"card {extra_class}".strip()
    return f'<section class="{cls}"{attrs}>{inner}</section>'


def heading(
    text: str, *, link: tuple[str, str] | None = None, note: str = "", style: str = ""
) -> str:
    """Título de painel (h2) com um link opcional à direita (arquivo, texto)."""
    right = ""
    if link is not None:
        right = f'<a href="{h.plain(link[0])}">{h.plain(link[1])}</a>'
    elif note:
        right = f"<span>{h.plain(note)}</span>"
    attrs = f' style="{h.plain(style)}"' if style else ""
    return f'<h2 class="h"{attrs}>{h.plain(text)} {right}</h2>'


def row(
    kind: MarkerKind | None,
    body: str,
    *,
    end: str = "",
    first: bool = False,
) -> str:
    """Linha: marcador, frase e valor ou link à direita (opcional). `body` e `end` são HTML."""
    style = ' style="border-top: 0"' if first else ""
    lead = marker(kind) if kind else ""
    return f'<div class="r"{style}>{lead}<span>{body}</span>{end}</div>'


def owner_row(owner: str, text: str) -> str:
    """Passo com dono: coluna de 96 px com quem faz, em azul."""
    return (
        f'<div class="r"><span class="who">{h.plain(owner)}</span>'
        f"<span>{h.plain(text)}</span></div>"
    )


def terminal(text: str, *, limit: int = 2400) -> str:
    """Bloco de terminal para texto do sistema testado: sempre como texto, nunca como marcação."""
    return f'<pre class="term">{h.block(text, limit)}</pre>'


def bar(parts: Sequence[tuple[float, str]], aria: str, *, style: str = "") -> str:
    """Barra empilhada de 16 px: partes (largura relativa, variável de cor) com `role="img"`."""
    total = sum(width for width, _ in parts) or 1.0
    cells = "".join(
        f'<i style="width: {width / total * 100:.2f}%; background: var(--{color})"></i>'
        for width, color in parts
        if width > 0
    )
    attrs = f' style="{h.plain(style)}"' if style else ""
    return f'<div class="stack"{attrs} role="img" aria-label="{h.plain(aria)}">{cells}</div>'


def not_measured(why: str) -> str:
    """Traço com a explicação, para dado que não existe (nunca zero)."""
    return f'<span class="mu">— não medido</span> <span class="sm mu">{h.plain(why)}</span>'


# ---------------------------------------------------------------- casca


def crumbs(name: str, when: str, links: PanelLinks, *, when_href: str = "summary.html") -> str:
    """Caminho do alto: `hdast / Produto / data · hora`.

    Cada pedaço é link relativo e só vira texto quando a página de destino não existe
    (`PanelLinks` com `None`). `name` e `when` chegam em texto cru; aqui são escapados.
    """

    def piece(text: str, href: str | None) -> str:
        if href is None:
            return f'<span class="crumb">{text}</span>'
        return f'<a href="{h.plain(href)}">{text}</a>'

    return (
        '<div class="brand"><i></i>'
        f'{piece("hdast", links.products)}<span class="sep">/</span>'
        f"{piece(h.ident(name), links.product)}"
        '<span class="sep">/</span>'
        f'<a class="here" href="{h.plain(when_href)}">{h.plain(when)}</a></div>'
    )


def _crumbs(view: PanelView) -> str:
    ident = view.identity
    return crumbs(ident.product_name, fmt_datetime(ident.started_at), view.links)


def tabs_nav(tabs: Sequence[TabItem], current: str | None) -> str:
    """Menu de abas; a aba `current` ganha `aria-current="page"`."""
    items: list[str] = []
    for tab in tabs:
        if not tab.enabled:
            items.append(
                '<span class="off" aria-disabled="true" title="Aparece quando o teste terminar">'
                f"{h.plain(tab.label)}</span>"
            )
            continue
        count = ""
        if tab.count is not None:
            grey = ' style="background: var(--s2); color: var(--mu)"' if tab.count == 0 else ""
            count = f'<span class="cnt"{grey}>{tab.count}</span>'
        here = ' class="on" aria-current="page"' if tab.file == current else ""
        items.append(f'<a{here} href="{h.plain(tab.file)}">{h.plain(tab.label)}{count}</a>')
    return f'<nav class="tabs" aria-label="Telas do painel">{"".join(items)}</nav>'


def _status(view: PanelView) -> str:
    ident = view.identity
    tone, word = STATE_CHIP[view.verdict.kind]
    when = (
        f" · {fmt_duration(ident.duration_seconds)}" if ident.duration_seconds is not None else ""
    )
    fence = ""
    if ident.fence_mode:
        mode = _MODE_WORDS.get(ident.fence_mode, ident.fence_mode)
        fence = (
            '<a class="sm mu" style="text-decoration: none" href="coverage.html">'
            f"Cerca: {h.ident(mode)}</a>"
        )
    return (
        '<div style="margin-left: auto; display: flex; flex-wrap: wrap; gap: 8px 14px; '
        f'align-items: center; padding: 10px 0">{fence}{chip(word + when, tone)}</div>'
    )


def document(*, title: str, header: str, main: str, refresh_seconds: int | None = None) -> str:
    """Documento HTML completo: política de conteúdo, estilo, `header` e `main` já escapados.

    `refresh_seconds` liga a recarga automática (`<meta http-equiv="refresh">`); a política de
    conteúdo (CSP) não restringe esse recarregamento e não muda por causa dele.
    """
    reload = (
        f'<meta http-equiv="refresh" content="{int(refresh_seconds)}">\n'
        if refresh_seconds is not None
        else ""
    )
    return (
        '<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n{reload}'
        f"<title>{h.plain(title)}</title>\n<style>\n{STYLE}</style>\n</head>\n<body>\n"
        f'<div class="tp">\n<header class="top">\n{header}\n</header>\n'
        f'<main class="pg">\n{main}\n</main>\n'
        f'<footer class="foot">{h.plain(_FOOTER)}</footer>\n</div>\n</body>\n</html>\n'
    )


def status_box(chips_html: str) -> str:
    """Canto direito do alto (cerca, hora da gravação e etiqueta de estado), já escapado."""
    return (
        '<div style="margin-left: auto; display: flex; flex-wrap: wrap; gap: 8px 14px; '
        f'align-items: center; padding: 10px 0">{chips_html}</div>'
    )


def render_page(
    view: PanelView, *, current: str, tabs: Sequence[TabItem], title: str, main: str
) -> str:
    """Página completa: casca, menu e o `<main>` que a aba entregou.

    Args:
        view: Visão do teste (o caminho e o estado do alto vêm dela).
        current: Arquivo da aba atual (ganha `aria-current="page"`).
        tabs: Abas, na ordem do menu.
        title: Título da aba (vai no `<title>` junto com o produto).
        main: Conteúdo do `<main>`, já escapado.
    """
    name = h.ident(view.identity.product_name)
    header = "\n".join((_crumbs(view), tabs_nav(tabs, current), _status(view)))
    return document(title=f"{title} · {name}", header=header, main=main)
