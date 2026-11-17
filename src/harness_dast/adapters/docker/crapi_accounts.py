"""Cadastro das contas sintéticas do crAPI pelo loopback e MailHog locais."""

import hashlib
import quopri
import re
import time
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from harness_dast.domain.errors import ExternalToolError

_VEHICLE = re.compile(r"VIN:\s*([A-Z0-9]{17}).*?Pincode:\s*(\d{4})", re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")


class _Response(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Token(_Response):
    token: str


class _Raw(_Response):
    To: list[str]
    Data: str


class _Message(_Response):
    Raw: _Raw


class _Messages(_Response):
    items: list[_Message]


class CrapiAccountProvisioner:
    """Cadastra duas contas em portas fixas de loopback, sem revelar respostas ou segredos."""

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Recebe transporte e espera substituíveis nos testes."""
        self._transport = transport
        self._sleep = sleep

    def provision(self, credentials: dict[str, str]) -> None:
        """Cadastra contas e veículos; falhas são traduzidas sem o conteúdo externo."""
        try:
            with httpx.Client(transport=self._transport, timeout=30, trust_env=False) as client:
                for label in ("A", "B"):
                    self._account(client, label, credentials)
        except (httpx.HTTPError, ValidationError, ValueError, KeyError):
            raise ExternalToolError(
                "Não foi possível cadastrar as contas sintéticas do crAPI.",
                hint="Confira a saúde do crAPI e MailHog e recrie a pilha.",
            ) from None

    def _account(self, client: httpx.Client, label: str, credentials: dict[str, str]) -> None:
        email = credentials[f"CRAPI_USER_{label}_EMAIL"]
        password = credentials[f"CRAPI_USER_{label}_PASSWORD"]
        web = "http://127.0.0.1:28888"
        number = "55" + str(
            int(hashlib.sha256(email.encode()).hexdigest()[:12], 16) % 100000000
        ).zfill(8)
        _post(
            client,
            f"{web}/identity/api/auth/signup",
            {
                "name": f"Lab {label}",
                "email": email,
                "number": number,
                "password": password,
            },
        )
        token = _Token.model_validate(
            _post(
                client,
                f"{web}/identity/api/auth/login",
                {
                    "email": email,
                    "password": password,
                },
            )
        ).token
        _post(client, f"{web}/identity/api/v2/vehicle/resend_email", {}, token)
        vin, pin = self._vehicle(client, email)
        _post(
            client,
            f"{web}/identity/api/v2/vehicle/add_vehicle",
            {"vin": vin, "pincode": pin},
            token,
        )

    def _vehicle(self, client: httpx.Client, email: str) -> tuple[str, str]:
        for _ in range(20):
            response = client.get("http://127.0.0.1:28025/api/v2/messages")
            response.raise_for_status()
            messages = _Messages.model_validate(response.json())
            for message in messages.items:
                if any(email.lower() in recipient.lower() for recipient in message.Raw.To):
                    text = quopri.decodestring(message.Raw.Data.encode()).decode(errors="replace")
                    match = _VEHICLE.search(" ".join(_TAGS.sub(" ", text).split()))
                    if match:
                        return match.group(1), match.group(2)
            self._sleep(1)
        raise ValueError("E-mail do veículo ausente")


def _post(client: httpx.Client, url: str, body: dict[str, str], token: str = "") -> object:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post(url, json=body, headers=headers)
    response.raise_for_status()
    return response.json() if response.content else {}
