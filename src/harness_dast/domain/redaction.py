"""Redação de evidência: nada do que vem do ZAP ou do alvo é gravado sem passar por aqui.

A evidência crua do ZAP contém o token e senhas em claro (spike, Q5). Todo texto que a CLI
grava (alertas brutos, requisição e resposta de evidência, achados) passa por estas funções:

- cabeçalhos de autenticação, cookies, chaves de API e tokens CSRF têm o valor trocado;
- JWT, `Bearer`/`Basic`, CPF, e-mail e sequências longas parecidas com token são trocados em
  QUALQUER lugar (URL, cabeçalho, corpo);
- corpos JSON têm os valores de campos com nome de senha/token/segredo trocados; corpos em
  formulário e texto livre têm os pares `nome=valor` sensíveis trocados;
- segredos registrados na execução (`mask`) são trocados mesmo que escapem das regras;
- ANSI, controle e bidi são removidos, e tudo é cortado em tamanho fixo DEPOIS da redação.

Redação por padrões é uma rede de segurança, não uma garantia: um segredo sem forma conhecida
e fora do registro pode passar. Por isso o registro de segredos da execução é aplicado sempre.
Este módulo é puro.
"""

import json
import re
import unicodedata
from collections.abc import Callable, Mapping
from typing import Final

from harness_dast.domain.api_schema import ApiModel, JsonValue
from harness_dast.domain.zap_messages import ZapMessage

MASK: Final = "***"
HEADER_CAP: Final = 3000
BODY_CAP: Final = 2000
FIELD_CAP: Final = 2000
_PRE_CAP: Final = 20_000
_MAX_DEPTH: Final = 8

_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
_SCHEME_TOKEN = re.compile(r"(?i)\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]{8,}")
_CPF = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LONG_TOKEN = re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9_+/=-]*\d)[A-Za-z0-9_+/=-]{24,}")
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.?")
_PAIR = re.compile(
    r"(?i)(\b(?:[\w-]*(?:password|passwd|senha|pwd|secret|token|apikey|api[_-]key|csrf|xsrf|"
    r"authorization|credential|session)[\w-]*)\b[\"']?\s*[:=]\s*[\"']?)"
    r"((?:(?:Bearer|Basic|Token|Digest|Negotiate)\s+)?)([^&\s\"',;}\]]+)"
)
_SENSITIVE_KEY_PARTS: Final = (
    "password",
    "passwd",
    "senha",
    "pwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "apikey",
    "api_key",
    "credential",
    "session",
    "csrf",
    "xsrf",
    "private_key",
    "access_key",
    "bearer",
    "auth",
)
_SENSITIVE_QUERY: Final = ("token", "key", "secret", "password", "senha", "auth", "session", "sig")

type Masker = Callable[[str], str]


class EvidenceMessage(ApiModel):
    """Requisição e resposta de uma mensagem do ZAP, já redigidas e cortadas.

    Attributes:
        message_id: Identificador da mensagem no ZAP.
        request_header: Cabeçalho da requisição (linha de requisição incluída).
        request_body: Corpo da requisição.
        response_header: Cabeçalho da resposta.
        response_body: Corpo da resposta.
        truncated: Se algum campo foi cortado no limite.
    """

    message_id: int
    request_header: str = ""
    request_body: str = ""
    response_header: str = ""
    response_body: str = ""
    truncated: bool = False


def strip_control(text: str, *, keep_newlines: bool = True) -> str:
    """Remove ANSI, controle, formatação (bidi, largura zero) e uso privado.

    Com `keep_newlines`, a quebra de linha fica (para blocos de cabeçalho); o retorno de
    carro some e a tabulação vira espaço. Separadores Unicode de linha e parágrafo viram
    espaço.
    """
    cleaned: list[str] = []
    for char in _ANSI.sub("", text):
        category = unicodedata.category(char)
        if char == "\n" and keep_newlines:
            cleaned.append(char)
        elif char in "\r\t\n" or category in {"Zl", "Zp"}:
            cleaned.append(" " if char != "\r" else "")
        elif not category.startswith("C"):
            cleaned.append(char)
    return "".join(cleaned)


def _is_sensitive_name(name: str) -> bool:
    lowered = name.lower().replace("-", "_")
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def is_sensitive_name(name: str) -> bool:
    """Diz se o NOME de um campo, cabeçalho ou opção indica segredo (senha, token, cookie...)."""
    return _is_sensitive_name(name)


def redact_text(text: str, mask: Masker) -> str:
    """Troca segredos registrados e padrões conhecidos em texto livre (sem cortar)."""
    value = mask(text)
    # O esquema (`Bearer`, `Basic`...) fica; o que é trocado é a credencial que vem depois dele.
    value = _PAIR.sub(lambda m: m.group(1) + m.group(2) + MASK, value)
    value = _SCHEME_TOKEN.sub(lambda m: f"{m.group(1)} {MASK}", value)
    for pattern in (_JWT, _EMAIL, _CPF, _LONG_TOKEN):
        value = pattern.sub(MASK, value)
    return mask(value)


def _cut(text: str, size: int) -> tuple[str, bool]:
    return (text, False) if len(text) <= size else (text[: size - 1] + "…", True)


def _redact_json(value: JsonValue, key: str, mask: Masker, depth: int) -> JsonValue:
    if key and _is_sensitive_name(key) and value is not None:
        return MASK
    if isinstance(value, str):
        return redact_text(strip_control(value, keep_newlines=False), mask)
    if isinstance(value, dict) and depth < _MAX_DEPTH:
        return {
            redact_text(name, mask): _redact_json(item, name, mask, depth + 1)
            for name, item in value.items()
        }
    if isinstance(value, list) and depth < _MAX_DEPTH:
        return [_redact_json(item, key, mask, depth + 1) for item in value]
    return "…" if isinstance(value, dict | list) else value


def redact_url(url: str, mask: Masker) -> str:
    """Redige uma URL: credenciais embutidas e valores de consulta sensíveis."""
    base, sep, query = url.partition("?")
    base = re.sub(r"(?<=://)[^/@\s]*@", f"{MASK}@", base)
    if sep:
        pairs = []
        for part in query.split("&"):
            name, eq, _ = part.partition("=")
            sensitive = any(word in name.lower() for word in _SENSITIVE_QUERY)
            pairs.append(f"{name}={MASK}" if eq and sensitive else part)
        query = "&".join(pairs)
    return redact_text(base + sep + query, mask)


def _redact_header_line(line: str, mask: Masker) -> str:
    name, colon, _ = line.partition(":")
    if colon and _is_sensitive_name(name):
        return f"{name}: {MASK}"
    return redact_text(line, mask)


def redact_header_block(block: str, mask: Masker) -> tuple[str, bool]:
    """Redige um bloco de cabeçalho HTTP (primeira linha e pares `Nome: valor`)."""
    lines = strip_control(block[:_PRE_CAP]).splitlines()
    if not lines:
        return "", False
    first = redact_url(lines[0], mask)
    rest = [_redact_header_line(line, mask) for line in lines[1:] if line.strip()]
    return _cut("\n".join([first, *rest]), HEADER_CAP)


def redact_body(body: str, mask: Masker, cap: int = BODY_CAP) -> tuple[str, bool]:
    """Redige um corpo (JSON, formulário ou texto) e o corta em `cap` caracteres."""
    text = body[:_PRE_CAP].strip()
    if not text:
        return "", False
    if text[0] in "{[":
        try:
            parsed: JsonValue = json.loads(mask(text))
        except (ValueError, RecursionError):
            pass
        else:
            dumped = json.dumps(_redact_json(parsed, "", mask, 0), ensure_ascii=False)
            return _cut(strip_control(dumped, keep_newlines=False), cap)
    return _cut(redact_text(strip_control(text), mask), cap)


def redact_message(message: ZapMessage, mask: Masker) -> EvidenceMessage:
    """Redige uma mensagem do ZAP inteira."""
    request_header, cut_a = redact_header_block(message.request_header, mask)
    response_header, cut_b = redact_header_block(message.response_header, mask)
    request_body, cut_c = redact_body(message.request_body, mask)
    response_body, cut_d = redact_body(message.response_body, mask)
    return EvidenceMessage(
        message_id=message.id,
        request_header=request_header,
        request_body=request_body,
        response_header=response_header,
        response_body=response_body,
        truncated=cut_a or cut_b or cut_c or cut_d,
    )


def redact_alert(alert: Mapping[str, str], mask: Masker) -> dict[str, str]:
    """Redige todos os campos de texto de um alerta bruto do ZAP, preservando as chaves."""
    cleaned: dict[str, str] = {}
    for name, value in alert.items():
        if name.lower() == "url":
            text = redact_url(strip_control(value, keep_newlines=False), mask)
        else:
            text = redact_text(strip_control(value, keep_newlines=True), mask)
        cleaned[name] = _cut(text, FIELD_CAP)[0]
    return cleaned
