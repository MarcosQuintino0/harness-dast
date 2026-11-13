"""`curl` reproduzível com marcadores no lugar dos segredos.

O comando é mostrado a pessoas que o colam num terminal, e a URL e o corpo vêm de um ataque
(dado do alvo, hostil). Por isso: o que vem do alvo entra SEMPRE entre aspas simples via
`shlex.quote` (nada é expandido pelo shell); o host vira `"$BASE_URL"`; autenticação e CSRF viram
`$TOKEN` e `$CSRF_TOKEN`; só o `Content-Type` seguro é repetido. Este módulo é puro.
"""

import re
import shlex
from typing import Final
from urllib.parse import urlsplit

from harness_dast.domain.finding import FindingEvidence

_REQUEST_LINE: Final = re.compile(r"^([A-Z]{3,10}) (\S+) HTTP/\d(?:\.\d)?$")
_SAFE_CONTENT_TYPE: Final = re.compile(r"^[A-Za-z0-9/+.-]{1,60}(?:; ?charset=[A-Za-z0-9-]{1,20})?$")


def _header_lines(block: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in block.splitlines()[1:]:
        name, _, value = line.partition(":")
        found[name.strip().lower()] = value.strip()
    return found


def _target(raw: str) -> str:
    parts = urlsplit(raw)
    path = parts.path or "/"
    return f"{path}?{parts.query}" if parts.query else path


def build_curl(
    evidence: FindingEvidence,
    *,
    auth_header: tuple[str, str] | None,
    csrf_header: str | None,
) -> str | None:
    """Monta o `curl` da melhor ocorrência; `None` sem a requisição de evidência.

    Args:
        evidence: Evidência já redigida (a requisição vem dela).
        auth_header: Nome do cabeçalho de autenticação do perfil e o valor com marcador
            (`("Authorization", "Bearer $TOKEN")`), ou `None` se não há autenticação. O nome
            já foi validado pelo perfil (`[A-Za-z0-9-]`).
        csrf_header: Nome do cabeçalho de CSRF do perfil (já validado), ou `None`.

    Returns:
        Comando em uma ou mais linhas, ou `None` quando a evidência não está disponível.
    """
    lines = evidence.request_header.splitlines()
    match = _REQUEST_LINE.match(lines[0]) if lines else None
    if not evidence.available or match is None:
        return None
    method, raw_target = match.group(1), match.group(2)
    headers = _header_lines(evidence.request_header)
    parts = [f'curl -i -X {shlex.quote(method)} "$BASE_URL"{shlex.quote(_target(raw_target))}']
    if auth_header and auth_header[0].lower() in headers:
        parts.append(f'-H "{auth_header[0]}: {auth_header[1]}"')
    if csrf_header and csrf_header.lower() in headers:
        parts.append(f'-H "{csrf_header}: $CSRF_TOKEN"')
    content_type = headers.get("content-type", "")
    if _SAFE_CONTENT_TYPE.match(content_type):
        parts.append(f'-H "Content-Type: {content_type}"')
    if evidence.request_body:
        parts.append(f"--data-raw {shlex.quote(evidence.request_body)}")
    return " \\\n  ".join(parts)
