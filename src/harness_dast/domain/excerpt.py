"""Trecho curto e neutralizado do corpo de uma resposta de falha, para o agente ler.

Tudo o que vem do alvo é DADO NÃO CONFIÁVEL: pode conter sequências de escape ANSI,
caracteres bidirecionais, ordens dirigidas ao agente ("ignore as instruções anteriores") e
segredos. Este módulo reduz o risco por construção, sem tentar "entender" o texto:

- tamanho máximo fixo (`EXCERPT_CAP`) e valores de texto de no máximo `VALUE_CAP`, o que
  limita o espaço disponível para uma instrução;
- remoção de ANSI e de TODO caractere de controle, formatação (inclui bidi e largura zero),
  separador de linha ou atribuído a uso privado;
- em JSON, os NOMES dos campos são preservados e os valores de texto passam por redação:
  JWT, CPF (formatado ou 11 dígitos), e-mail, sequências longas parecidas com token e
  qualquer valor cujo campo tenha nome sensível (`password`, `token`, `secret`...);
- valores registrados como segredo da execução (`mask`) são trocados por `***` mesmo que
  tenham passado pelas regras acima.

Não há como garantir que um texto curto não "pareça" uma instrução; por isso o chamador
sempre o entrega sob uma chave que o marca como dado do alvo. Este módulo é puro.
"""

import json
import re
import unicodedata
from collections.abc import Callable
from typing import Final

from harness_dast.domain.api_schema import JsonValue

EXCERPT_CAP: Final = 300
VALUE_CAP: Final = 80
KEY_CAP: Final = 40
MASK: Final = "***"
_MAX_DEPTH = 6

# Duplicam, de propósito, os padrões de observability/logging.py: o domínio não pode
# importar aquele pacote (contrato do import-linter).
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
_CPF = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LONG_TOKEN = re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9_+/=-]*\d)[A-Za-z0-9_+/=-]{24,}")
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.?")
_SENSITIVE_KEYS = (
    "password",
    "passwd",
    "senha",
    "token",
    "secret",
    "authorization",
    "cookie",
    "apikey",
    "api_key",
    "credential",
    "session",
)


def strip_unsafe_chars(text: str) -> str:
    """Remove ANSI e caracteres de controle, formatação, separadores de linha e uso privado.

    Quebras de linha e tabulações viram espaço, para o trecho nunca forjar linhas no
    terminal nem no log.
    """
    without_ansi = _ANSI.sub("", text)
    cleaned: list[str] = []
    for char in without_ansi:
        category = unicodedata.category(char)
        if char in "\n\r\t" or category in {"Zl", "Zp"}:
            cleaned.append(" ")
        elif not category.startswith("C"):
            cleaned.append(char)
    return "".join(cleaned)


def _redact_patterns(text: str) -> str:
    text = _JWT.sub(MASK, text)
    text = _EMAIL.sub(MASK, text)
    text = _CPF.sub(MASK, text)
    return _LONG_TOKEN.sub(MASK, text)


def _cut(text: str, size: int) -> str:
    return text if len(text) <= size else text[: size - 1] + "…"


def _clean_text(text: str, mask: Callable[[str], str], size: int) -> str:
    return _cut(mask(_redact_patterns(strip_unsafe_chars(text))), size)


def _is_sensitive(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in _SENSITIVE_KEYS)


def _sanitize_json(value: JsonValue, key: str, mask: Callable[[str], str], depth: int) -> JsonValue:
    if isinstance(value, str):
        return MASK if _is_sensitive(key) else _clean_text(value, mask, VALUE_CAP)
    if isinstance(value, dict) and depth < _MAX_DEPTH:
        result: dict[str, JsonValue] = {}
        for name, item in value.items():
            clean_name = _clean_text(name, mask, KEY_CAP)
            result[clean_name] = _sanitize_json(item, name, mask, depth + 1)
        return result
    if isinstance(value, list) and depth < _MAX_DEPTH:
        return [_sanitize_json(item, key, mask, depth + 1) for item in value[:10]]
    if isinstance(value, dict | list):
        return "…"
    return MASK if _is_sensitive(key) and value is not None else value


def sanitize_excerpt(body: bytes, mask: Callable[[str], str]) -> str:
    """Devolve um trecho seguro do corpo, com no máximo `EXCERPT_CAP` caracteres.

    Args:
        body: Corpo da resposta (já limitado em tamanho pelo cliente).
        mask: Troca por `***` os segredos conhecidos da execução (token, senhas).

    Returns:
        Texto sem controle/ANSI/bidi. JSON mantém os nomes dos campos e tem os valores
        redigidos; outro conteúdo é tratado como texto simples. Corpo vazio dá `""`.
    """
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    if text[0] in "{[":
        try:
            parsed: JsonValue = json.loads(text)
        except (ValueError, RecursionError):
            parsed = None
        else:
            dumped = json.dumps(_sanitize_json(parsed, "", mask, 0), ensure_ascii=False)
            return _clean_text(dumped, mask, EXCERPT_CAP)
    return _clean_text(text, mask, EXCERPT_CAP)
