"""Servidor HTTP real em 127.0.0.1 (biblioteca padrão, numa thread) para testar adaptadores.

Serve como alvo e também como proxy: o `http.server` entrega a linha de requisição como veio,
então uma requisição enviada "pelo proxy" chega com a URL absoluta em `target`.
"""

import ssl
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


@dataclass
class Received:
    """O que o servidor recebeu numa requisição."""

    method: str
    target: str
    headers: dict[str, str]
    body: bytes

    @property
    def path(self) -> str:
        """Caminho sem consulta, tanto para forma de origem quanto absoluta."""
        return urlsplit(self.target).path

    @property
    def query(self) -> str:
        return urlsplit(self.target).query

    @property
    def is_absolute(self) -> bool:
        return "://" in self.target


@dataclass
class Reply:
    """Resposta que o manipulador manda."""

    status: int = 200
    body: bytes = b""
    headers: list[tuple[str, str]] = field(default_factory=list)
    delay: float = 0.0
    drop: bool = False  # fecha a conexão sem responder (o ZAP real faz isso com chave errada)


type Handler = Callable[[Received], Reply]


@dataclass
class LocalServer:
    """Endereço do servidor e o registro do que ele recebeu."""

    host: str
    port: int
    scheme: str
    requests: list[Received] = field(default_factory=list)

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


def _make_handler(handler: Handler, server: LocalServer) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            received = Received(
                self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, body
            )
            server.requests.append(received)
            reply = handler(received)
            if reply.drop:
                self.close_connection = True
                return
            if reply.delay:
                threading.Event().wait(reply.delay)
            try:
                self.send_response(reply.status)
                for name, value in reply.headers:
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(reply.body)))
                self.end_headers()
                self.wfile.write(reply.body)
            except OSError:  # o cliente já desistiu (teste de tempo limite)
                return

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _serve  # noqa: N815

        def log_message(self, format: str, *args: object) -> None:
            return

    return _Handler


class _QuietServer(ThreadingHTTPServer):
    """Servidor que não imprime o rastro de conexões abortadas pelo cliente (testes de tempo)."""

    def handle_error(self, request: object, client_address: object) -> None:
        return


@contextmanager
def serve(handler: Handler, *, tls: tuple[str, str] | None = None) -> Iterator[LocalServer]:
    """Sobe o servidor numa porta livre e o derruba ao sair.

    Args:
        handler: Decide a resposta de cada requisição.
        tls: Par (certificado, chave) PEM para servir HTTPS.
    """
    info = LocalServer("127.0.0.1", 0, "https" if tls else "http")
    httpd = _QuietServer(("127.0.0.1", 0), _make_handler(handler, info))
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(*tls)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    info.port = httpd.server_address[1]
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield info
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def free_port() -> int:
    """Uma porta local sem ninguém escutando (conexão será recusada)."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
