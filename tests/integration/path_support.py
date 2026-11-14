"""Apoio dos testes de caminho no laboratório: HTTP cru (bytes exatos) e estado do piloto.

O `httpx` e a biblioteca padrão normalizam a URL (resolvem `..`, recodificam). Aqui o pedido vai por
`socket`, byte a byte, porque o objeto do teste é justamente o que o proxy e o servidor fazem com
a forma exata do caminho. Só fala com `127.0.0.1` (portas publicadas pelo laboratório).
"""

import json
import os
import socket
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROXY = ("127.0.0.1", 3128)
PILOT_API = ("127.0.0.1", 28080)
PILOT_MANAGEMENT = "http://127.0.0.1:29091"
PILOT_HOST = "clinica-piloto:8080"


@dataclass(frozen=True)
class RawReply:
    """Resposta lida do socket.

    Attributes:
        status: Código HTTP.
        headers: Cabeçalhos em minúsculas.
        body: Corpo decodificado (UTF-8, com substituição).
    """

    status: int
    headers: Mapping[str, str]
    body: str

    @property
    def reason(self) -> str:
        """Valor de `X-Hdast-Reason` (vazio se a resposta não veio do proxy de escopo)."""
        return self.headers.get("x-hdast-reason", "")


def _exchange(address: tuple[str, int], first_line: str, headers: list[str]) -> RawReply:
    with socket.create_connection(address, timeout=60) as sock:
        text = (
            first_line + "\r\n" + "".join(h + "\r\n" for h in headers) + "Connection: close\r\n\r\n"
        )
        sock.sendall(text.encode("latin-1"))
        data = b""
        while chunk := sock.recv(65536):
            data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split(" ")[1])
    parsed = {
        line.split(":", 1)[0].lower(): line.split(":", 1)[1].strip()
        for line in lines[1:]
        if ":" in line
    }
    return RawReply(status, parsed, body.decode("utf-8", "replace"))


def via_proxy(path: str, token: str | None = None, method: str = "GET") -> RawReply:
    """Envia pelo proxy de escopo (forma absoluta, o que o ZAP faz) com o caminho EXATO."""
    headers = [f"Host: {PILOT_HOST}"]
    if token:
        headers.append(f"Authorization: Bearer {token}")
    return _exchange(PROXY, f"{method} http://{PILOT_HOST}{path} HTTP/1.1", headers)


def direct(path: str, token: str | None = None, method: str = "GET") -> RawReply:
    """Envia direto à porta publicada do piloto (127.0.0.1:28080), sem proxy, caminho EXATO."""
    headers = [f"Host: {PILOT_HOST}"]
    if token:
        headers.append(f"Authorization: Bearer {token}")
    return _exchange(PILOT_API, f"{method} {path} HTTP/1.1", headers)


def pilot_state() -> dict[str, object]:
    """Estado de avaliação do piloto (porta de gestão, loopback)."""
    with urllib.request.urlopen(PILOT_MANAGEMENT + "/internal/eval/state", timeout=20) as response:  # noqa: S310 - loopback fixo
        loaded = json.load(response)
    assert isinstance(loaded, dict)
    return loaded


def pilot_requests() -> dict[str, int]:
    """Contagem por rota do piloto (`requests_by_endpoint`)."""
    found = pilot_state()["requests_by_endpoint"]
    assert isinstance(found, dict)
    return {str(k): int(v) for k, v in found.items()}


def pilot_token(env: Mapping[str, str]) -> str:
    """Login do admin sintético do laboratório, pelo proxy (POST /api/auth/login)."""
    body = json.dumps(
        {"username": env["PILOT_ADMIN_USERNAME"], "password": env["PILOT_ADMIN_PASSWORD"]}
    ).encode()
    with socket.create_connection(PROXY, timeout=60) as sock:
        head = (
            f"POST http://{PILOT_HOST}/api/auth/login HTTP/1.1\r\nHost: {PILOT_HOST}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        )
        sock.sendall(head.encode("latin-1") + body)
        data = b""
        while chunk := sock.recv(65536):
            data += chunk
    text = data.partition(b"\r\n\r\n")[2].decode("utf-8", "replace")
    payload = json.loads(
        text[text.index("{") : text.rindex("}") + 1]
    )  # tolera o corpo em pedaços (chunked)
    return str(payload["access_token"])


def artifacts_dir() -> Path | None:
    """Pasta onde os testes de laboratório guardam tabelas (variável `HDAST_LAB_ARTIFACTS`)."""
    folder = os.environ.get("HDAST_LAB_ARTIFACTS")
    if not folder:
        return None
    path = Path(folder)
    path.mkdir(parents=True, exist_ok=True)
    return path
