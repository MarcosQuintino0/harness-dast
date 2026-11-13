"""Semeia contas de teste sinteticas no crAPI do laboratorio (apenas biblioteca padrao).

Roda NA MAQUINA DO COORDENADOR, depois do `docker compose up` do crAPI, contra o loopback
(`127.0.0.1:28888`) e o mailhog local (`127.0.0.1:28025`). Nao e usado pelo agente nem pelo `hdast`.
Para cada conta: cadastro, login, pedido do e-mail com VIN e PIN (lido no mailhog local) e cadastro
do veiculo, que o crAPI exige para a maior parte dos endpoints.

Uso:
    python lab/crapi/seed.py --out <arquivo.json>

O arquivo recebe os pares NOME -> valor das variaveis que o perfil le por `secret_ref`
(`CRAPI_USER_A_EMAIL`, `CRAPI_USER_A_PASSWORD`, `CRAPI_USER_B_EMAIL`, `CRAPI_USER_B_PASSWORD`).
Guarde-o fora do repositorio; os valores sao sorteados a cada execucao.
"""

import argparse
import json
import quopri
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

LOOPBACK = ("http://127.0.0.1:", "http://localhost:")
VEHICLE_PATTERN = re.compile(r"VIN:\s*([A-Z0-9]{17}).*?Pincode:\s*(\d{4})", re.DOTALL)
TAGS = re.compile(r"<[^>]+>")
ACCOUNTS = ("A", "B")
MAIL_ATTEMPTS = 20
HTTP_TIMEOUT_SECONDS = 30


class SeedError(Exception):
    """Falha ao semear: a mensagem diz o que houve."""


def parse_vehicle(raw_message: str) -> tuple[str, str]:
    """Extrai (VIN, PIN) do e-mail cru do mailhog (HTML em quoted-printable).

    Raises:
        SeedError: A mensagem nao traz VIN e PIN.
    """
    text = TAGS.sub(" ", quopri.decodestring(raw_message.encode()).decode(errors="replace"))
    found = VEHICLE_PATTERN.search(" ".join(text.split()))
    if found is None:
        raise SeedError("O e-mail do mailhog nao traz VIN e PIN.")
    return found.group(1), found.group(2)


def new_password() -> str:
    """Senha que cumpre a politica do crAPI (maiuscula, minuscula, digito e simbolo)."""
    return "Aa1#" + secrets.token_hex(8)


def _request(method: str, url: str, body: dict[str, Any] | None, token: str | None) -> Any:
    if not url.startswith(LOOPBACK):
        raise SeedError(f"Recuso falar com {url}: so o loopback do laboratorio.")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)  # noqa: S310 - esquema conferido acima
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
            payload = response.read().decode()
    except urllib.error.HTTPError as error:
        raise SeedError(
            f"{method} {url} deu {error.code}: {error.read().decode()[:200]}"
        ) from error
    except OSError as error:
        raise SeedError(f"{method} {url} falhou: {error}. O crAPI esta de pe?") from error
    return json.loads(payload) if payload else {}


def _vehicle_mail(mail: str, email: str) -> str:
    for _ in range(MAIL_ATTEMPTS):
        messages = _request("GET", f"{mail}/api/v2/messages", None, None).get("items", [])
        for message in messages:
            if email in message.get("To", []) or email in str(message.get("Raw", {}).get("To")):
                try:
                    parse_vehicle(message["Raw"]["Data"])
                except SeedError:
                    continue
                return str(message["Raw"]["Data"])
        time.sleep(1)
    raise SeedError(f"Nao chegou e-mail com o veiculo de {email} no mailhog.")


def seed_account(
    web: str, mail: str, label: str, given: dict[str, str] | None = None
) -> dict[str, str]:
    """Cadastra uma conta com veiculo e devolve as variaveis dela (e-mail e senha).

    Com `given` (variaveis ja sorteadas, como as do `prepare` da avaliacao), usa esses valores.
    """
    given = given or {}
    email = (
        given.get(f"CRAPI_USER_{label}_EMAIL")
        or f"lab.{label.lower()}.{secrets.token_hex(3)}@example.com"
    )
    password = given.get(f"CRAPI_USER_{label}_PASSWORD") or new_password()
    number = "55" + "".join(secrets.choice("0123456789") for _ in range(8))
    _request(
        "POST",
        f"{web}/identity/api/auth/signup",
        {"name": f"Lab {label}", "email": email, "number": number, "password": password},
        None,
    )
    token = _request(
        "POST", f"{web}/identity/api/auth/login", {"email": email, "password": password}, None
    )["token"]
    _request("POST", f"{web}/identity/api/v2/vehicle/resend_email", {}, token)
    vin, pincode = parse_vehicle(_vehicle_mail(mail, email))
    _request(
        "POST",
        f"{web}/identity/api/v2/vehicle/add_vehicle",
        {"vin": vin, "pincode": pincode},
        token,
    )
    return {f"CRAPI_USER_{label}_EMAIL": email, f"CRAPI_USER_{label}_PASSWORD": password}


def main(argv: list[str] | None = None) -> int:
    """Semeia as contas e grava o arquivo de variaveis. Devolve 0, ou 2 em erro."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--use",
        type=Path,
        default=None,
        help="JSON com valores ja sorteados (ex.: sealed/secrets.json)",
    )
    parser.add_argument("--web", default="http://127.0.0.1:28888")
    parser.add_argument("--mail", default="http://127.0.0.1:28025")
    args = parser.parse_args(argv)
    variables: dict[str, str] = {}
    given = json.loads(args.use.read_text(encoding="utf-8")) if args.use else None
    try:
        for label in ACCOUNTS:
            variables.update(seed_account(args.web, args.mail, label, given))
    except SeedError as error:
        sys.stderr.write(f"erro: {error}\n")
        return 2
    args.out.write_text(json.dumps(variables, indent=2), encoding="utf-8")
    sys.stdout.write(
        f"{len(variables)} variaveis gravadas em {args.out} (nao mostrei os valores)\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
