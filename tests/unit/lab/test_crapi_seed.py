"""Semeador do crAPI: extracao de VIN e PIN, politica de senha e recusa fora do loopback."""

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

SEED = Path(__file__).resolve().parents[3] / "lab" / "crapi" / "seed.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("crapi_seed", SEED)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MAIL = (
    "Content-Type: text/html; charset=UTF-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n"
    "<p>Your vehicle information is <b>VIN:</b> 4ILKA33BRDC125835 and <b>Pincode:</b> 4219 =\r\n"
    "<br>Thank You</p>"
)


def test_parse_vehicle_reads_vin_and_pin_from_the_quoted_printable_html() -> None:
    assert _load().parse_vehicle(MAIL) == ("4ILKA33BRDC125835", "4219")


def test_parse_vehicle_rejects_a_mail_without_vehicle_data() -> None:
    module = _load()

    with pytest.raises(module.SeedError):
        module.parse_vehicle("Subject: oi\r\n\r\nsem veiculo")


def test_new_password_meets_the_crapi_policy() -> None:
    password = _load().new_password()

    assert re.search(r"[A-Z]", password)
    assert re.search(r"[a-z]", password)
    assert re.search(r"\d", password)
    assert re.search(r"[^A-Za-z0-9]", password)


def test_seed_refuses_to_talk_to_anything_but_the_loopback() -> None:
    module = _load()

    with pytest.raises(module.SeedError, match="loopback"):
        module.seed_account("http://crapi.example.com", "http://127.0.0.1:1", "A")
