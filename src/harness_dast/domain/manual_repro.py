"""Dados de "Como reproduzir à mão" de um achado (aba "Falhas" do painel).

Sai só da evidência que o `findings.json` já guarda (requisição e resposta, redigidas pelo
`redaction`). Nada é buscado no alvo e nada novo é gravado. Regras, todas testadas:

- o endereço é relativo (`/api/...`) e a base é sempre o marcador `$BASE_URL`;
- cabeçalho de autenticação ou segredo vira o marcador `$TOKEN` (CSRF, `$CSRF_TOKEN`); o
  painel nunca mostra token, senha ou cookie, e a ferramenta não os grava;
- cabeçalhos comuns de transporte somem e, dos demais, só o NOME aparece (o valor só quando é
  um `Content-Type` seguro);
- no lugar da credencial vai o apelido da conta (`user_a`), informado por quem chama;
- CPF, e-mail e telefone na evidência são mascarados por padrão, mesmo em ambiente de teste
  (decisão do painel; a redação do `findings.json` já cobre CPF e e-mail, e aqui entra também o
  telefone formatado e a garantia de que a regra vale para qualquer evidência);
- a resposta recebida é resumida: código de status, no máximo 40 linhas do corpo e o tamanho.

Sem evidência guardada, devolve `None`. Texto da evidência é dado do alvo: o painel o mostra
sempre como texto. Este módulo é puro.
"""

import re
from typing import Final
from urllib.parse import urlsplit

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.finding import Finding
from harness_dast.domain.redaction import is_sensitive_name, strip_control

BASE_URL_MARKER: Final = "$BASE_URL"
TOKEN_MARKER: Final = "$TOKEN"  # noqa: S105 - marcador de texto, nunca um segredo
CSRF_MARKER: Final = "$CSRF_TOKEN"
RESPONSE_LINE_CAP: Final = 40
_ROW_CAP: Final = 600

_REQUEST_LINE: Final = re.compile(r"^([A-Z]{3,10}) (\S+) HTTP/\d(?:\.\d)?$")
_STATUS_LINE: Final = re.compile(r"^HTTP/\d(?:\.\d)?\s+(\d{3})\b")
_SAFE_CONTENT_TYPE: Final = re.compile(r"^[A-Za-z0-9/+.-]{1,60}(?:; ?charset=[A-Za-z0-9-]{1,20})?$")
_HEADER_NAME: Final = re.compile(r"[A-Za-z0-9-]{1,60}")
_DROPPED_HEADERS: Final = frozenset(
    {
        "host",
        "content-length",
        "connection",
        "user-agent",
        "accept-encoding",
        "accept-language",
        "pragma",
        "cache-control",
        "origin",
        "referer",
        "upgrade-insecure-requests",
        "transfer-encoding",
    }
)
_CPF: Final = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
_EMAIL: Final = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE: Final = re.compile(r"(?<!\d)(?:\+55[ -]?)?\(?\d{2}\)?[ -]?9?\d{4}-\d{4}(?!\d)")
CPF_MASK: Final = "***.***.***-**"
EMAIL_MASK: Final = "***@***"
PHONE_MASK: Final = "(**) *****-****"


class ReproHeader(ApiModel):
    """Um cabeçalho da requisição de reprodução.

    Attributes:
        name: Nome do cabeçalho.
        value: Valor mostrável (marcador `$TOKEN`, `Content-Type` seguro) ou `None` quando só o
            nome aparece e quem reproduz copia o resto do navegador.
    """

    name: str
    value: str | None = None


class ManualRepro(ApiModel):
    """Passo a passo de reprodução à mão, em dados (o painel só os desenha).

    Attributes:
        method: Método HTTP.
        base_url: Sempre `$BASE_URL`.
        target: Caminho e consulta relativos, com dado pessoal mascarado.
        account: Apelido da conta que o teste usou (`user_a`), ou `None`.
        headers: Cabeçalhos a enviar, na ordem da requisição.
        body: Corpo (mascarado), ou `None` quando a requisição não teve.
        received_status: Código de status que o teste recebeu, ou `None` se não constar.
        response_excerpt: Até 40 linhas do corpo da resposta recebida (mascarado).
        response_total_lines: Quantas linhas o corpo gravado tem.
        response_cut: Se o trecho foi cortado (por tamanho gravado ou pelo limite de linhas).
        personal_data_masked: Se algum CPF, e-mail ou telefone foi mascarado.
    """

    method: str
    base_url: str = BASE_URL_MARKER
    target: str
    account: str | None = None
    headers: tuple[ReproHeader, ...] = ()
    body: str | None = None
    received_status: int | None = None
    response_excerpt: str = ""
    response_total_lines: int = 0
    response_cut: bool = False
    personal_data_masked: bool = False


def mask_personal_data(text: str) -> tuple[str, bool]:
    """Mascara CPF, e-mail e telefone formatado de um texto.

    Returns:
        O texto mascarado e se alguma coisa foi mascarada. O telefone só é reconhecido com
        hífen (`(11) 91234-5678`, `11 1234-5678`); número solto de 10 ou 11 dígitos pode ser
        qualquer coisa e não é tocado, exceto os 11 dígitos de CPF.
    """
    changed = False
    for pattern, mask in ((_EMAIL, EMAIL_MASK), (_CPF, CPF_MASK), (_PHONE, PHONE_MASK)):
        text, count = pattern.subn(mask, text)
        changed = changed or count > 0
    return text, changed


def _target_of(raw: str) -> str:
    parts = urlsplit(raw)
    path = parts.path or "/"
    return f"{path}?{parts.query}" if parts.query else path


def _marker_for(name: str, value: str) -> str | None:
    lowered = name.lower()
    if "csrf" in lowered or "xsrf" in lowered:
        return CSRF_MARKER
    if lowered == "authorization" and value.lower().startswith("bearer"):
        return f"Bearer {TOKEN_MARKER}"
    if is_sensitive_name(name):
        return TOKEN_MARKER
    return None


def _headers_of(block: str) -> tuple[ReproHeader, ...]:
    headers: list[ReproHeader] = []
    for line in block.splitlines()[1:]:
        name, sep, value = line.partition(":")
        name, value = name.strip(), value.strip()
        if not sep or not _HEADER_NAME.fullmatch(name) or name.lower() in _DROPPED_HEADERS:
            continue
        marker = _marker_for(name, value)
        if marker is not None:
            headers.append(ReproHeader(name=name, value=marker))
        elif name.lower() == "content-type" and _SAFE_CONTENT_TYPE.match(value):
            headers.append(ReproHeader(name=name, value=value))
        else:
            headers.append(ReproHeader(name=name))
    return tuple(headers)


def _status_of(response_header: str) -> int | None:
    first = response_header.splitlines()[0] if response_header else ""
    match = _STATUS_LINE.match(first.strip())
    return int(match.group(1)) if match else None


def _excerpt(body: str, *, stored_cut: bool) -> tuple[str, int, bool]:
    lines = strip_control(body).splitlines()
    clipped = [line if len(line) <= _ROW_CAP else line[: _ROW_CAP - 1] + "…" for line in lines]
    shown = clipped[:RESPONSE_LINE_CAP]
    return "\n".join(shown), len(lines), stored_cut or len(lines) > RESPONSE_LINE_CAP


def build_manual_repro(finding: Finding, *, account: str | None = None) -> ManualRepro | None:
    """Monta os dados de reprodução à mão a partir da evidência do achado.

    Args:
        finding: O achado, com a evidência já redigida.
        account: Apelido da conta que o teste usou (`user_a`); nunca credencial.

    Returns:
        Os dados, ou `None` quando a evidência não existe ou a linha da requisição não é
        legível.
    """
    evidence = finding.evidence
    lines = evidence.request_header.splitlines()
    match = _REQUEST_LINE.match(lines[0].strip()) if lines else None
    if not evidence.available or match is None:
        return None
    target, target_masked = mask_personal_data(strip_control(_target_of(match.group(2))))
    body_text = evidence.request_body
    body, body_masked = mask_personal_data(strip_control(body_text)) if body_text else (None, False)
    response, response_masked = mask_personal_data(evidence.response_body)
    excerpt, total, cut = _excerpt(response, stored_cut=evidence.truncated)
    return ManualRepro(
        method=match.group(1),
        target=target,
        account=account,
        headers=_headers_of(evidence.request_header),
        body=body,
        received_status=_status_of(evidence.response_header),
        response_excerpt=excerpt,
        response_total_lines=total,
        response_cut=cut,
        personal_data_masked=target_masked or body_masked or response_masked,
    )
