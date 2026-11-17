"""Alvo em memória que esgota o orçamento com recuos das etapas de sessão."""

from collections import Counter
from urllib.parse import urlsplit

from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.confirmation_rig import confirmation_target


class RetryingSessionTarget:
    """Exige quatro pedidos por busca CSRF e login, sem usar rede ou relógio real."""

    def __init__(self) -> None:
        """Inicia a contagem independente de cada rota da sessão."""
        self._attempts: Counter[str] = Counter()

    def __call__(self, request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        """Responde 429 nas três primeiras tentativas de cada grupo de quatro."""
        path = urlsplit(request.url).path
        if path in {"/api/csrf", "/api/auth/login"}:
            self._attempts[path] += 1
            if self._attempts[path] % 4:
                return HttpResponse(status=429, retry_after="0")
            if path == "/api/csrf":
                jar["XSRF-TOKEN"] = "csrf-de-teste"
                return HttpResponse(status=200)
        return confirmation_target(request, jar)
