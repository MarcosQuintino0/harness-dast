"""Markdown seguro para texto que vem do alvo, do ZAP ou do agente.

Tudo o que o relatório mostra e que não é texto nosso passa por uma destas funções: nada pode
virar título, link, imagem, HTML, tabela quebrada nem fechar um bloco de código. Instruções
escritas em texto livre continuam sendo texto: por isso o relatório as marca como dado e as
mostra em bloco, mas nenhuma função "entende" ordens. Este módulo é puro.
"""

import re
from typing import Final

from harness_dast.domain.redaction import strip_control

_SPECIAL: Final = re.compile(r"[\\`*_{}\[\]()<>#+!|~&$]")
_URL_SCHEME: Final = re.compile(r":(?=//)")
_WWW: Final = re.compile(r"(?i)(?<![\w])www\.")
_BACKTICKS: Final = re.compile(r"`+")
_MAX_INLINE: Final = 400


def _longest_backticks(text: str) -> int:
    return max((len(run) for run in _BACKTICKS.findall(text)), default=0)


def escape_inline(text: str, limit: int = _MAX_INLINE) -> str:
    """Escapa texto para parágrafo, item de lista ou célula de tabela (uma linha, cortada)."""
    flat = " ".join(strip_control(text, keep_newlines=False).split())
    if len(flat) > limit:
        flat = flat[: limit - 1] + "…"
    escaped = _SPECIAL.sub(lambda m: "\\" + m.group(0), flat)
    escaped = _URL_SCHEME.sub(r"\\:", escaped)
    return _WWW.sub(r"www\\.", escaped)


def code_span(text: str, limit: int = _MAX_INLINE) -> str:
    """Trecho de código em linha, com crases suficientes para o conteúdo não escapar dele."""
    flat = " ".join(strip_control(text, keep_newlines=False).split())
    if len(flat) > limit:
        flat = flat[: limit - 1] + "…"
    ticks = "`" * (_longest_backticks(flat) + 1)
    padded = f" {flat} " if flat.startswith("`") or flat.endswith("`") else flat
    return f"{ticks}{padded}{ticks}" if flat else "``"


def fenced(text: str, language: str = "") -> str:
    """Bloco de código cercado por uma cerca mais longa que qualquer sequência de crases dentro."""
    body = strip_control(text, keep_newlines=True).rstrip("\n")
    fence = "`" * max(3, _longest_backticks(body) + 1)
    tag = language if re.fullmatch(r"[a-z]{0,12}", language) else ""
    return f"{fence}{tag}\n{body}\n{fence}"
