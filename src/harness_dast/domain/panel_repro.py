"""Bloco "Como reproduzir à mão" e a prova de uma falha (aba Falhas do painel). Módulo puro.

Fiel a `docs/design/execution-panel/screens/findings.html`: três passos (pegar um token, mandar o
pedido, comparar a resposta), o pedido e a resposta que o teste recebeu como TEXTO no bloco de
terminal, e o comando para colar. Regras de segurança, todas testadas:

- o endereço do sistema e o token são SEMPRE os marcadores `$BASE_URL` e `$TOKEN` (CSRF:
  `$CSRF_TOKEN`); o painel nunca mostra token, senha nem cookie, e a conta aparece só pelo
  apelido (`user_a`);
- tudo que veio do sistema testado (caminho, corpo, resposta) entra como texto escapado e
  redigido (`html_safe`); o destaque do ataque é feito sobre o texto JÁ escapado, nunca sobre o
  original;
- dado pessoal (CPF, e-mail, telefone) já foi mascarado em `build_manual_repro`;
- o comando `curl` só é montado quando o endereço e o corpo cabem entre aspas sem escapar nada
  (senão a página diz que não montou, em vez de oferecer um comando que quebra).
"""

import html
import re
from typing import Final
from urllib.parse import quote

from harness_dast.domain import html_safe as h
from harness_dast.domain.manual_repro import BASE_URL_MARKER, ManualRepro
from harness_dast.domain.panel_format import fmt_date, plural
from harness_dast.domain.panel_layout import row
from harness_dast.domain.panel_model import PanelFinding, PanelView

_NO_BODY_METHODS: Final = frozenset({"GET", "HEAD", "DELETE", "OPTIONS"})
_UNSAFE_IN_QUOTES: Final = re.compile(r'["`$\\\r\n]')
_UNSAFE_IN_SINGLE: Final = re.compile(r"['\r\n]")
_AMBER: Final = 'class="hl" style="color: var(--am); background: var(--ams)"'
_PLACEHOLDERS: Final = frozenset({BASE_URL_MARKER, "$TOKEN", "$CSRF_TOKEN"})
_MIN_PLAIN_NEEDLE: Final = 4
_REPORT: Final = "../report.html"
_SERVER_ERROR: Final = 500


def _needles(text: str) -> tuple[str, ...]:
    """Formas do texto que podem aparecer no endereço ou no corpo (cru e codificado)."""
    forms = {text, quote(text, safe=""), quote(text)}
    return tuple(sorted((item for item in forms if item), key=len, reverse=True))


def mark_first(escaped: str, needles: tuple[str, ...], css: str = 'class="hl"') -> str:
    """Destaca a primeira ocorrência de um dos trechos num texto JÁ escapado.

    O trecho também é escapado antes da busca; trecho curto só de letras ou números é ignorado
    (poderia cair no meio de uma entidade como `&amp;`). O resto do texto não muda.
    """
    best: tuple[int, int] | None = None
    for needle in needles:
        wanted = html.escape(needle, quote=True)
        if len(wanted) < _MIN_PLAIN_NEEDLE and wanted.isalnum():
            continue
        at = escaped.find(wanted)
        if at >= 0 and (best is None or at < best[0] or (at == best[0] and len(wanted) > best[1])):
            best = (at, len(wanted))
    if best is None:
        return escaped
    start, size = best
    end = start + size
    return f"{escaped[:start]}<span {css}>{escaped[start:end]}</span>{escaped[end:]}"


def _amber(text: str) -> str:
    return f"<span {_AMBER}>{h.plain(text)}</span>"


def _marker_value(value: str) -> str:
    """Valor de cabeçalho: o marcador de segredo em amarelo; o resto como texto."""
    parts = re.split(r"(\$[A-Z_]+)", value)
    return "".join(
        _amber(part) if part in _PLACEHOLDERS else h.plain(part) for part in parts if part
    )


def request_html(repro: ManualRepro) -> str:
    """O pedido como texto no bloco de terminal: linha do pedido, cabeçalhos e corpo.

    Os marcadores (`$BASE_URL`, `$TOKEN`, `$CSRF_TOKEN`) são texto NOSSO e saem sem redação
    (a redação confundiria `Bearer $TOKEN` com um token); o nome e o valor de cada cabeçalho já
    passaram pelas regras de `build_manual_repro` (nome só com letras, números e hífen; valor só
    marcador ou `Content-Type` seguro). Endereço e corpo vêm do alvo e passam pelo `html_safe`.
    """
    target = h.text(repro.target, 600)
    if repro.attack:
        target = mark_first(target, _needles(repro.attack))
    lines = [f"{h.plain(repro.method)} {h.plain(repro.base_url)}{target}"]
    for header in repro.headers:
        value = h.plain(header.value) if header.value else "…"
        lines.append(f"{h.plain(header.name)}: {value}")
    if repro.body:
        body = h.block(repro.body, 1200)
        lines.extend(("", mark_first(body, _needles(repro.attack)) if repro.attack else body))
    return "\n".join(lines)


def curl_html(repro: ManualRepro) -> str | None:
    """Comando `curl` com marcadores (HTML escapado), ou `None` se não cabe entre aspas."""
    if _UNSAFE_IN_QUOTES.search(repro.target):
        return None
    parts = ["curl -i -X", h.plain(repro.method), f"&quot;{h.plain(repro.base_url)}"]
    parts[-1] += f"{h.text(repro.target, 600)}&quot;"
    for header in repro.headers:
        if header.value:
            plain_value = header.value.replace("$TOKEN", "").replace("$CSRF_TOKEN", "")
            if _UNSAFE_IN_QUOTES.search(plain_value):
                return None
            parts.append(f"-H &quot;{h.plain(header.name)}: {h.plain(header.value)}&quot;")
    if repro.body:
        if _UNSAFE_IN_SINGLE.search(repro.body):
            return None
        parts.append(f"--data-raw &#x27;{h.text(repro.body, 1200)}&#x27;")
    return " ".join(parts)


def _term(inner_html: str) -> str:
    return f'<pre class="term">{inner_html}</pre>'


def _step_token(repro: ManualRepro) -> str:
    who = f"<b>{h.ident(repro.account)}</b>" if repro.account else "uma conta de teste da carta"
    return (
        '<div class="sub" style="flex: 1 1 300px">'
        '<b><span class="stepn">1</span>Pegue um token</b>'
        f'<span class="sm">Abra o sistema de teste no navegador e entre com {who}.</span>'
        '<span class="sm">Aperte <b>F12</b>, abra a aba <b>Rede</b> (Network) e clique em '
        "qualquer coisa do sistema.</span>"
        '<span class="sm">Clique num pedido da lista e copie o texto que vem depois de '
        '<span class="mono">Authorization: Bearer</span>. Esse texto é o token.</span>'
        '<span class="sm mu">O painel nunca mostra o token: a ferramenta não grava senha nem '
        "token. Ele vale por pouco tempo.</span></div>"
    )


def _kv(label: str, value: str, *, first: bool = False) -> str:
    style = ' style="border-top: 0"' if first else ""
    return f'<div class="r"{style}><span class="kvl">{h.plain(label)}</span>{value}</div>'


def _address(repro: ManualRepro) -> str:
    escaped = h.text(repro.target, 600)
    target = mark_first(escaped, _needles(repro.attack)) if repro.attack else escaped
    return f'<span class="mono">{_amber(repro.base_url)}{target}</span>'


def _headers(repro: ManualRepro) -> str:
    if not repro.headers:
        return '<span class="mu">nenhum além dos que o navegador já manda</span>'
    lines = []
    for header in repro.headers:
        value = _marker_value(header.value) if header.value else '<span class="mu">…</span>'
        lines.append(f"{h.ident(header.name, 60)}: {value}")
    return f'<span class="mono">{"<br>".join(lines)}</span>'


def _body(repro: ManualRepro) -> str:
    if repro.body is None:
        why = (
            "vazio: pedido do tipo " + repro.method + " não leva corpo"
            if repro.method in _NO_BODY_METHODS
            else "vazio: este pedido foi mandado sem corpo"
        )
        return f'<span class="mu">{h.plain(why)}</span>'
    escaped = h.block(repro.body, 1200)
    marked = mark_first(escaped, _needles(repro.attack)) if repro.attack else escaped
    return f'<pre class="term" style="flex: 1; min-width: 0; margin: 0">{marked}</pre>'


def _step_request(repro: ManualRepro) -> str:
    blank_headers = any(item.value is None for item in repro.headers)
    legend = (
        "Em amarelo: o que você preenche. O endereço do sistema de teste é o mesmo que você abre "
        "no navegador (está na carta). Em vermelho: o ataque."
        + (
            " Onde está “…”, copie o valor do pedido que você viu no navegador."
            if blank_headers
            else ""
        )
    )
    return (
        '<div class="sub" style="flex: 1.4 1 380px">'
        '<b><span class="stepn">2</span>Mande este pedido</b>'
        + _kv("Método", f'<span class="mono">{h.ident(repro.method, 12)}</span>', first=True)
        + _kv("Endereço (URL)", _address(repro))
        + _kv("Cabeçalhos", _headers(repro))
        + _kv("Corpo (body)", _body(repro))
        + f'<span class="sm mu">{h.plain(legend)}</span></div>'
    )


def _step_compare(repro: ManualRepro, view: PanelView) -> str:
    when = fmt_date(view.identity.started_at)
    status = repro.received_status
    if status is None:
        same = "Resposta igual à da prova abaixo"
    else:
        kind = "Erro" if status >= _SERVER_ERROR else "Resposta"
        same = f"{kind} {status} igual ao da prova abaixo"
    rows = (
        row(
            "gr",
            f"<b>{h.plain(same)}:</b> a falha continua. Foi o que o teste recebeu no teste de "
            f"{h.plain(when)}.",
            first=True,
        ),
        row(
            "ok",
            "<b>Resposta diferente, como lista vazia ou erro 400 de validação:</b> pode ter "
            "sido corrigida.",
        ),
        row("am", "<b>401 ou 403:</b> o token venceu. Pegue outro no passo 1."),
        row("no", "<b>Qualquer outra coisa:</b> pare e mostre ao time de dev."),
    )
    return (
        '<div class="sub" style="flex: 1.2 1 320px">'
        f'<b><span class="stepn">3</span>Compare a resposta</b>{"".join(rows)}</div>'
    )


def _response_block(item: PanelFinding, repro: ManualRepro) -> str:
    evidence = item.evidence
    head = evidence.response_header.splitlines()[0] if evidence and evidence.response_header else ""
    text = "\n".join(part for part in (head, repro.response_excerpt) if part)
    proof = (evidence.zap_evidence if evidence else "").strip()
    note = ""
    if repro.response_cut:
        note = (
            '<p class="sm mu" style="margin-top: 6px">'
            "cortado: mostramos as primeiras linhas de "
            f"{plural(repro.response_total_lines, 'linha gravada', 'linhas gravadas')}"
            f'; a prova de cada falha está no <a href="{_REPORT}">relatório completo</a>.</p>'
        )
    inner = h.block(text, 2400)
    shown = (
        _term(mark_first(inner, _needles(proof)) if proof else inner)
        if text
        else '<p class="mu">A resposta gravada não tem corpo.</p>'
    )
    return (
        '<div><p class="sm mu" style="margin-bottom: 6px">A resposta que o teste recebeu (veio do '
        "sistema testado; é mostrada como texto):</p>" + shown + note + "</div>"
    )


def _request_block(repro: ManualRepro) -> str:
    return (
        '<div><p class="sm mu" style="margin-bottom: 6px">O pedido que o teste mandou (os '
        "segredos estão trocados por marcadores; o endereço do sistema também):</p>"
        + _term(request_html(repro))
        + "</div>"
    )


def _paste_blocks(repro: ManualRepro) -> str:
    curl = curl_html(repro)
    left = (
        '<p class="sm mu" style="margin-bottom: 6px">Pronto para colar no <b>PowerShell</b> '
        "(escreva <b>curl.exe</b>) ou no terminal. Antes, defina as duas variáveis: "
        '<span class="mono">$BASE_URL</span> (o endereço do sistema de teste) e '
        '<span class="mono">$TOKEN</span> (o token do passo 1):</p>'
        + (
            f'<pre class="term copy"><span class="c">{curl}</span></pre>'
            if curl
            else '<p class="mu">Não montamos o comando: o endereço ou o corpo têm caracteres que '
            "quebrariam o comando. Use o pedido acima.</p>"
        )
    )
    right = (
        '<p class="sm mu" style="margin-bottom: 6px">No <b>Postman</b> ou <b>Insomnia</b>: novo '
        f"pedido {h.ident(repro.method, 12)}, cole o endereço e ponha o token em Auth, tipo "
        "Bearer Token.</p>"
        '<pre class="term copy"><span class="c">'
        f"{h.plain(repro.base_url)}{h.text(repro.target, 600)}</span></pre>"
    )
    return (
        '<div class="g">'
        f'<div style="flex: 1 1 420px; min-width: 0">{left}</div>'
        f'<div style="flex: 1 1 420px; min-width: 0">{right}</div></div>'
    )


def render_repro(item: PanelFinding, view: PanelView) -> str:
    """O bloco "Como reproduzir à mão" de UMA falha (HTML já escapado)."""
    head = (
        '<h2 class="h" style="font-size: 17px">Como reproduzir à mão '
        "<span>para você conferir se a falha faz sentido</span></h2>"
    )
    if item.origin == "authz":
        return (
            '<div style="display: flex; flex-direction: column; gap: 14px">'
            + head
            + '<p class="mu">Esta falha vem da comparação entre duas contas: o programa repete um '
            "pedido com a outra conta e compara as respostas, sem guardar o pedido nem a resposta "
            "inteiros. Por isso não há passo a passo para reproduzir à mão aqui.</p>"
            + (
                '<p class="sm"><b>O que o teste observou:</b> '
                f"{h.text(item.authz_evidence, 600)}</p>"
                if item.authz_evidence
                else ""
            )
            + "</div>"
        )
    repro = item.repro
    if repro is None:
        return (
            '<div style="display: flex; flex-direction: column; gap: 14px">'
            + head
            + '<p class="mu">A ferramenta não guardou o pedido e a resposta desta falha, então não '
            "há passo a passo. Peça uma nova varredura desta função para gravar a prova.</p></div>"
        )
    damaged = (
        '<p class="sm"><b>Atenção:</b> o endereço gravado perdeu um pedaço quando a ferramenta '
        "escondeu dados secretos. O caminho abaixo foi refeito pelo modelo da função e pode não "
        "ser exatamente o que foi enviado: confira com o time de dev.</p>"
        if repro.target_damaged
        else ""
    )
    masked = (
        '<p class="sm mu">CPF, e-mail e telefone que apareciam na prova foram trocados por '
        'máscaras (<span class="mono">***</span>).</p>'
        if repro.personal_data_masked
        else ""
    )
    return (
        '<div style="display: flex; flex-direction: column; gap: 14px">'
        + head
        + damaged
        + '<div class="g">'
        + f"{_step_token(repro)}{_step_request(repro)}{_step_compare(repro, view)}</div>"
        + _request_block(repro)
        + _response_block(item, repro)
        + masked
        + _paste_blocks(repro)
        + "</div>"
    )
