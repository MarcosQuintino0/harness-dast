"""Contrato de `hdast authz`: envelope, códigos de saída e artefatos, com um servidor HTTP real.

Um servidor em 127.0.0.1 faz de ZAP, de proxy e de alvo ao mesmo tempo (como em
`test_cli_probe_commands.py`). O alvo tem uma falha de BOLA: qualquer conta com token lê
qualquer `/api/doc/{id}`. O `probe` roda de verdade e o `authz` repete o pedido com a outra
conta do mesmo papel.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode
from tests.fakes.approvals import approve_product_on_disk
from tests.fakes.local_server import LocalServer, Received, Reply, serve
from tests.fakes.profile_data import valid_profile_data

pytestmark = pytest.mark.contract

ZAP_KEY = "chave-zap-do-contrato-9"
PASSWORDS = {"alice": "SenhaDaAlice-777", "bruno": "SenhaDoBruno-888"}
TOKENS = {"alice": "tok-ALICE-CONTRATO-123", "bruno": "tok-BRUNO-CONTRATO-456"}
HASH = "$2b$10$HASH-DO-CONTRATO-QUE-NAO-PODE-VAZAR"
OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Contrato", "version": "1"},
    "paths": {
        "/api/doc/{id}": {
            "get": {
                "operationId": "doc",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}
                ],
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "integer"},
                                        "nome": {"type": "string"},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    },
}


def handler(r: Received) -> Reply:
    if r.path.startswith("/JSON/"):
        payloads = {
            "/JSON/core/view/version/": {"version": "2.17.0"},
            "/JSON/context/action/newContext/": {"contextId": "1"},
            "/JSON/replacer/view/rules/": {"rules": []},
        }
        return Reply(200, json.dumps(payloads.get(r.path, {"Result": "OK"})).encode())
    if r.path == "/api/auth/login":
        creds = json.loads(r.body or b"{}")
        who = creds.get("username", "")
        if who in PASSWORDS and creds.get("password") == PASSWORDS[who]:
            return Reply(200, json.dumps({"access_token": TOKENS[who]}).encode())
        return Reply(401, b"{}")
    if r.headers.get("authorization") not in {f"Bearer {t}" for t in TOKENS.values()}:
        return Reply(401, b"{}")
    if r.path.startswith("/api/doc/"):
        body = {"id": int(r.path.rsplit("/", 1)[1]), "nome": "documento", "passwordHash": HASH}
        return Reply(200, json.dumps(body).encode())
    return Reply(200, b'{"ok":true}')


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in (
        "HDAST_ZAP_PROXY_URL",
        "HDAST_AUTH_PROXY_URL",
        "HDAST_PRODUCTS_DIR",
        "HDAST_LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HDAST_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("HDAST_ZAP_API_KEY", ZAP_KEY)
    monkeypatch.setenv("CONTRATO_A_LOGIN", "alice")
    monkeypatch.setenv("CONTRATO_A_SENHA", PASSWORDS["alice"])
    monkeypatch.setenv("CONTRATO_B_LOGIN", "bruno")
    monkeypatch.setenv("CONTRATO_B_SENHA", PASSWORDS["bruno"])


def write_product(products: Path, server: LocalServer, **authz: Any) -> None:
    data = valid_profile_data("demo")
    data["environment"]["base_url"] = server.base_url
    data["openapi"] = "./openapi.yml"
    data["scope"]["allow"] = [
        {
            "host": "127.0.0.1",
            "scheme": "http",
            "port": server.port,
            "paths": ["/api/**"],
            "methods": ["GET", "POST", "PUT"],
            "allow_local": True,
        }
    ]
    data["scope"]["deny_paths"] = []
    data["auth"]["token_path"] = "/api/auth/login"  # noqa: S105 - caminho, não um segredo
    data["auth"]["accounts"] = [
        {
            "alias": alias,
            "role": "usuario",
            "username": {"secret_ref": f"env:CONTRATO_{key}_LOGIN"},
            "password": {"secret_ref": f"env:CONTRATO_{key}_SENHA"},
        }
        for alias, key in (("user_a", "A"), ("user_b", "B"))
    ]
    data["probe"] = {"health_path": "/api/saude"}
    if authz:
        data["authz"] = authz
    folder = products / "demo"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "target.yml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (folder / "openapi.yml").write_text(yaml.safe_dump(OPENAPI), encoding="utf-8")
    approve_product_on_disk(products, "demo")  # o que uma pessoa faria no terminal


@contextmanager
def environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **authz: Any
) -> Iterator[tuple[LocalServer, Path]]:
    products = tmp_path / "produtos"
    products.mkdir(exist_ok=True)
    with serve(handler) as server:
        write_product(products, server, **authz)
        monkeypatch.setenv("HDAST_ZAP_BASE_URL", server.base_url)
        yield server, products


def invoke(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = run_app(build_app(), list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def invoke_json(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any], str]:
    code, out, err = invoke(capsys, "--json", *args)
    return code, json.loads(out), err


def probe(capsys: pytest.CaptureFixture[str], products: Path) -> str:
    code, envelope, _ = invoke_json(capsys, "probe", "demo", "--products-dir", str(products))
    assert code == ExitCode.OK
    return str(envelope["run_id"])


AUTHZ_KEYS = {
    "schema_version",
    "run_id",
    "product",
    "dry_run",
    "status",
    "stop_message",
    "started_at",
    "finished_at",
    "requests_sent",
    "created_resources",
    "accounts",
    "access_matrix",
    "checks",
    "findings",
    "not_tested",
    "limits",
    "notice",
}


def test_authz_finds_bola_and_excessive_data_and_writes_authz_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, err = invoke_json(
            capsys, "authz", "demo", "--run", run_id, "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert set(envelope) == {"schema_version", "ok", "run_id", "data"}
    assert envelope["ok"] is True
    assert envelope["run_id"] == run_id
    data = envelope["data"]
    assert set(data) == AUTHZ_KEYS
    assert data["status"] == "completed"
    techniques = {f["technique"] for f in data["findings"]}
    assert techniques == {"authz_horizontal", "authz_excessive_data"}
    assert {f["origin"] for f in data["findings"]} == {"authz"}
    assert [c["check"] for c in data["checks"]] == [
        "cors",
        "horizontal",
        "excessive_data",
        "anonymous_access",
        "tampered_token",
        "vertical",
        "access_matrix",
        "mass_assignment",
        "horizontal_write",
    ]
    on_disk = json.loads((tmp_path / "runs" / run_id / "authz.json").read_text(encoding="utf-8"))
    assert on_disk == data
    everything = json.dumps(envelope) + err + json.dumps(on_disk)
    for secret in (*PASSWORDS.values(), *TOKENS.values(), ZAP_KEY, HASH):
        assert secret not in everything


def test_authz_audit_lines_carry_the_authz_operation_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        invoke_json(capsys, "authz", "demo", "--run", run_id, "--products-dir", str(products))

    lines = (tmp_path / "runs" / run_id / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines]
    assert any(e["operation_id"] == "authz:doc" for e in entries)
    seqs = [e["seq"] for e in entries if e["phase"] == "decision"]
    assert len(seqs) == len(set(seqs))


def test_authz_public_operations_silence_bola_but_not_the_field_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path, public_operations=["doc"]) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, _ = invoke_json(
            capsys, "authz", "demo", "--run", run_id, "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert {f["technique"] for f in envelope["data"]["findings"]} == {"authz_excessive_data"}


def test_authz_check_flag_only_reduces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path, disabled_checks=["horizontal"]) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, _ = invoke_json(
            capsys,
            "authz",
            "demo",
            "--run",
            run_id,
            "--check",
            "horizontal",
            "--products-dir",
            str(products),
        )

    assert code == ExitCode.OK
    assert envelope["data"]["findings"] == []
    assert envelope["data"]["requests_sent"] == 0
    assert {c["status"] for c in envelope["data"]["checks"]} == {"disabled"}


def test_authz_dry_run_plans_without_sending_or_writing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        run_id = probe(capsys, products)
        before = len(server.requests)
        code, envelope, _ = invoke_json(
            capsys, "authz", "demo", "--run", run_id, "--dry-run", "--products-dir", str(products)
        )
        after = len(server.requests)

    assert code == ExitCode.OK
    assert "run_id" not in envelope
    assert envelope["data"]["dry_run"] is True
    assert envelope["data"]["requests_sent"] == 0
    assert before == after
    assert not (tmp_path / "runs" / run_id / "authz.json").exists()


def test_authz_human_output_is_a_portuguese_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        code, out, _ = invoke(
            capsys, "authz", "demo", "--run", run_id, "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert "Authz de demo" in out
    assert "ACHADO" in out
    assert "authz_horizontal" in out


@pytest.mark.parametrize(
    "extra",
    [["--check", "inexistente"], ["--run", "../fora"], ["--run", "2026-01-01T00-00-00Z-demo-abcd"]],
)
def test_authz_bad_arguments_are_a_usage_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        run_id = probe(capsys, products)
        sent = len(server.requests)
        args = ["authz", "demo", "--run", run_id, "--products-dir", str(products)]
        if extra[0] == "--run":
            args[3] = extra[1]
        else:
            args += extra
        code, envelope, _ = invoke_json(capsys, *args)
        assert len(server.requests) == sent

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"


def test_authz_requires_the_run_option(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        code, _, _ = invoke(capsys, "authz", "demo", "--products-dir", str(products))

    assert code == ExitCode.USAGE


def test_authz_of_a_run_without_probe_json_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        code, envelope, _ = invoke_json(
            capsys,
            "authz",
            "demo",
            "--run",
            "2026-01-01T00-00-00Z-demo-abcd",
            "--products-dir",
            str(products),
        )

    assert code == ExitCode.USAGE
    assert "probe.json" in json.dumps(envelope)


def test_authz_check_mass_assignment_without_the_letter_is_not_tested_and_not_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, _ = invoke_json(
            capsys,
            "authz",
            "demo",
            "--run",
            run_id,
            "--check",
            "mass_assignment",
            "--products-dir",
            str(products),
        )

    assert code == ExitCode.OK
    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["findings"] == []
    assert data["requests_sent"] == 0
    reasons = {(n["check"], n["reason"]) for n in data["not_tested"]}
    assert ("mass_assignment", "writes_not_authorized") in reasons
    mass = next(c for c in data["checks"] if c["check"] == "mass_assignment")
    assert mass["status"] == "skipped"


def test_authz_accepts_the_access_checks_by_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, _ = invoke_json(
            capsys,
            "authz",
            "demo",
            "--run",
            run_id,
            "--check",
            "anonymous_access",
            "--check",
            "tampered_token",
            "--products-dir",
            str(products),
        )

    assert code == ExitCode.OK
    statuses = {c["check"]: c["status"] for c in envelope["data"]["checks"]}
    assert statuses["anonymous_access"] != "disabled"
    assert statuses["tampered_token"] != "disabled"  # noqa: S105 - nome de verificação
    assert statuses["horizontal"] == "disabled"


def test_authz_check_with_an_unknown_name_still_lists_the_new_ones_in_the_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, _ = invoke_json(
            capsys,
            "authz",
            "demo",
            "--run",
            run_id,
            "--check",
            "token_forjado",
            "--products-dir",
            str(products),
        )

    assert code == ExitCode.USAGE
    assert "anonymous_access" in json.dumps(envelope)
    assert "tampered_token" in json.dumps(envelope)


def test_authz_dry_run_lists_the_access_candidates_without_sending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        run_id = probe(capsys, products)
        before = len(server.requests)
        code, envelope, _ = invoke_json(
            capsys,
            "authz",
            "demo",
            "--run",
            run_id,
            "--dry-run",
            "--check",
            "anonymous_access",
            "--check",
            "tampered_token",
            "--products-dir",
            str(products),
        )
        after = len(server.requests)

    assert code == ExitCode.OK
    assert before == after
    by_name = {c["check"]: c for c in envelope["data"]["checks"]}
    assert by_name["anonymous_access"]["candidates"] >= 1
    assert by_name["tampered_token"]["candidates"] >= 1


def test_authz_check_horizontal_write_is_accepted_and_needs_the_letter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, _ = invoke_json(
            capsys,
            "authz",
            "demo",
            "--run",
            run_id,
            "--check",
            "horizontal_write",
            "--products-dir",
            str(products),
        )

    assert code == ExitCode.OK
    data = envelope["data"]
    assert data["findings"] == []
    assert data["requests_sent"] == 0
    reasons = {(n["check"], n["reason"]) for n in data["not_tested"]}
    assert ("horizontal_write", "writes_not_authorized") in reasons
    write = next(c for c in data["checks"] if c["check"] == "horizontal_write")
    assert write["status"] == "skipped"
    assert "escrita não autorizada" in write["message"]


def test_authz_dry_run_of_horizontal_write_sends_nothing_even_with_the_letter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path, allow_writes=True) as (server, products):
        run_id = probe(capsys, products)
        before = len(server.requests)
        code, envelope, _ = invoke_json(
            capsys,
            "authz",
            "demo",
            "--run",
            run_id,
            "--dry-run",
            "--check",
            "horizontal_write",
            "--products-dir",
            str(products),
        )
        after = len(server.requests)

    assert code == ExitCode.OK
    assert before == after
    write = next(c for c in envelope["data"]["checks"] if c["check"] == "horizontal_write")
    assert write["status"] == "skipped"
    assert write["candidates"] == 0
