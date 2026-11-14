"""Escape de HTML para texto que vem do alvo, do ZAP ou do agente. Módulo puro.

Tudo o que a página mostra e que não é texto nosso passa por `text` ou `block`: caracteres de
controle, ANSI e bidi saem, segredos conhecidos são trocados por `***` (a mesma rede de
segurança da redação, aplicada de novo por garantia, ANTES do corte para não deixar metade de
um segredo), o texto é cortado e os cinco caracteres
especiais do HTML (`& < > " '`) viram entidades. O resultado serve tanto como conteúdo de
elemento quanto como valor de atributo entre aspas. Nada aqui "entende" HTML: o texto do alvo
nunca vira marcação.
"""

import html
import re
from typing import Final

from harness_dast.domain.redaction import redact_text, strip_control

_CODE: Final = re.compile(r"`([A-Za-z0-9_.-]{1,40})`")
_DEFAULT_INLINE: Final = 400
_DEFAULT_BLOCK: Final = 2400


def _identity(value: str) -> str:
    return value


def _cut(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def text(value: str, limit: int = _DEFAULT_INLINE) -> str:
    """Texto de uma linha, redigido, cortado e escapado."""
    flat = " ".join(strip_control(value, keep_newlines=False).split())
    return html.escape(_cut(redact_text(flat, _identity), limit), quote=True)


def block(value: str, limit: int = _DEFAULT_BLOCK) -> str:
    """Texto de várias linhas (para `<pre>`), redigido, cortado e escapado."""
    cleaned = strip_control(value, keep_newlines=True).strip("\n")
    return html.escape(_cut(redact_text(cleaned, _identity), limit), quote=True)


def ident(value: str, limit: int = _DEFAULT_INLINE) -> str:
    """Identificador (execução, operação, caminho de modelo): escapado e cortado, sem redação.

    A redação por padrão mascararia ids longos legítimos (`run_id`, operações do OpenAPI);
    o escape continua valendo, e nada disso é segredo: são nomes do perfil e do OpenAPI.
    """
    flat = " ".join(strip_control(value, keep_newlines=False).split())
    return html.escape(_cut(flat, limit), quote=True)


def tagged(value: str) -> str:
    """Texto NOSSO com termos técnicos entre crases: cada um vira uma etiqueta cinza.

    A frase vem primeiro e o código fica ao lado, na etiqueta (`deny_paths`). Só entra em
    etiqueta um nome curto de letras, dígitos, ponto, sublinhado e hífen: nada de marcação.
    """
    return _CODE.sub(
        lambda found: f'<span class="chip ch-mu">{found.group(1)}</span>',
        html.escape(value, quote=True),
    )


def plain(value: str) -> str:
    """Escapa texto NOSSO ou derivado de identificador (sem redação nem corte)."""
    return html.escape(value, quote=True)
