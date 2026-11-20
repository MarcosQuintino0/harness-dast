"""Valida a origem local de controle usada exclusivamente na captura de estratégia."""

from ipaddress import ip_address
from urllib.parse import SplitResult, urlsplit

from harness_dast.domain.errors import ConfigError


def _loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _port(url: SplitResult) -> int | None:
    port = url.port
    if port is not None:
        return port
    return {"http": 80, "https": 443}.get(url.scheme)


def ensure_capture_control_url(control_url: str, target_url: str) -> None:
    """Exige controle loopback isolado da porta do alvo local, sem resolver DNS.

    Não prova que o serviço local é ZAP nem detecta proxies que encaminham ao alvo.
    URLs malformadas ou sem origem conhecida são recusadas sem repetir a entrada.
    """
    try:
        control = urlsplit(control_url)
        target = urlsplit(target_url)
        control_port, target_port = _port(control), _port(target)
        invalid = (
            not control_url.isprintable()
            or control_url != control_url.strip()
            or control.scheme not in {"http", "https"}
            or not _loopback(control.hostname)
            or control.username is not None
            or control.password is not None
            or control.path not in {"", "/"}
            or bool(control.query or control.fragment)
            or control_port is None
            or control_port == 0
            or target.scheme not in {"http", "https"}
            or target.hostname is None
            or target_port is None
            or (_loopback(target.hostname) and control_port == target_port)
        )
    except ValueError:
        invalid = True
    if invalid:
        raise ConfigError(
            "Origem de controle da captura inválida ou coincidente com o alvo local.",
            hint="Configure o controle ZAP em localhost ou IP loopback, em porta distinta do alvo.",
        )
