"""Identificador do recurso criado e alvo do GET que o lê (ADR 0040)."""

import json

import pytest

from harness_dast.domain.authz_created import created_identifier, created_read_exchange
from harness_dast.domain.probe_exchange import ExchangeRecord

BASE = "https://api.hml.acme-teste.net.br"
READER = ExchangeRecord(
    operation_id="lerMedico",
    method="GET",
    path="/api/medicos/{id}",
    target="/api/medicos/7?x=1",
    account="adm",
    status=200,
)


def ident(
    location: str | None = None, body: bytes = b"", reader: ExchangeRecord = READER
) -> str | None:
    return created_identifier(location=location, body=body, reader=reader, base_url=BASE)


@pytest.mark.parametrize(
    "location",
    ["/api/medicos/12", f"{BASE}/api/medicos/12", "/api/medicos/12?x=1", "/api/medicos/ab-C_9"],
)
def test_a_location_of_the_same_resource_gives_the_identifier(location: str) -> None:
    assert ident(location) is not None
    assert ident(location) == location.split("?")[0].rsplit("/", 1)[1]


@pytest.mark.parametrize(
    "location",
    [
        "https://outro.example.org/api/medicos/12",
        "http://api.hml.acme-teste.net.br/api/medicos/12",
        f"{BASE}.evil.com/api/medicos/12",
        "//outro.example.org/api/medicos/12",
        "/api/medicos/../me",
        "/api/medicos/12/extra",
        "/api/pacientes/12",
        "/api/medicos/",
        "/api/medicos/1 2",
        "/api/medicos/%2e%2e",
        "/api/medicos/" + "9" * 65,
        "/api/medicos/a\\b",
        "api/medicos/12",
        "",
        "ftp://x/api/medicos/1",
        "/api/medicos/" + "1" * 3000,
    ],
)
def test_a_malformed_or_foreign_location_is_refused(location: str) -> None:
    assert ident(location) is None


def test_without_location_the_marker_name_or_id_in_the_body_is_used() -> None:
    assert ident(None, json.dumps({"id": 31}).encode()) == "31"
    assert ident(None, json.dumps({"ID": "abc"}).encode()) == "abc"
    marker = READER.model_copy(update={"path": "/api/medicos/{medicoId}"})
    assert ident(None, json.dumps({"medico_id": 5}).encode(), marker) == "5"


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"   ",
        b"{oops",
        b"[1]",
        b'"x"',
        b"{}",
        b'{"nome": "a"}',
        b'{"id": null}',
        b'{"id": true}',
        b'{"id": "a/b"}',
        b'{"id": "../x"}',
        b'{"id": 1.5}',
        b'{"id": {"a": 1}}',
        b'{"id": ""}',
        b"\xff\xfe",
        json.dumps({"id": "x" * 65}).encode(),
    ],
)
def test_a_missing_or_unsafe_id_in_the_body_is_refused(body: bytes) -> None:
    assert ident(None, body) is None


def test_the_location_wins_over_the_body() -> None:
    assert ident("/api/medicos/8", json.dumps({"id": 99}).encode()) == "8"


def test_a_bad_location_falls_back_to_the_body() -> None:
    assert ident("https://outro.example.org/api/medicos/8", json.dumps({"id": 99}).encode()) == "99"


def test_the_read_target_replaces_the_last_segment_and_drops_the_query() -> None:
    read = created_read_exchange(READER, "12")

    assert read is not None
    assert read.target == "/api/medicos/12"
    assert read.method == "GET"
    assert read.account == "adm"
    assert read.body is None


@pytest.mark.parametrize("identifier", ["", "a/b", "..", "a b", "x" * 65, "a?b", "%2e"])
def test_an_unsafe_identifier_never_builds_a_target(identifier: str) -> None:
    assert created_read_exchange(READER, identifier) is None
