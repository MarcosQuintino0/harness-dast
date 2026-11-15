"""Contrato de `hdast negative`: envelope, códigos de saída e artefatos, com um servidor HTTP real.

Um servidor em 127.0.0.1 faz de ZAP, de proxy e de alvo ao mesmo tempo (como em
`test_cli_authz.py`). `GET /api/lista` exige `limite` (inteiro de 1 a 100), `ordem` (`asc` ou
`desc`) e `busca` (até 5 caracteres). Fora do contrato, responde 400 (`MODE["lista"] =
"validate"`), aceita tudo (`"lax"`), falha com 500 (`"crash"`) ou fica fora do ar (`"down"`). O
`probe` roda de verdade e o `negative` repete o pedido com um valor que o OpenAPI proíbe.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest
import yaml

from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode
from tests.fakes.approvals import approve_product_on_disk
from tests.fakes.local_server import LocalServer, Received, Reply, serve
from tests.fakes.profile_data import valid_profile_data

pytestmark = pytest.mark.contract

ZAP_KEY = "chave-zap-do-contrato-9"
PASSWORD = "SenhaDaAlice-777"  # noqa: S105 - sentinela de teste, não um segredo
TOKEN = "tok-ALICE-CONTRATO-123"  # noqa: S105 - sentinela de teste, não um segredo
MODE = {"lista": "validate"}
OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Contrato", "version": "1"},
    "paths": {
        "/api/lista": {
            "get": {
                "operationId": "lista",
                "parameters": [
                    {
                        "name": "limite",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    {
                        "name": "ordem",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "enum": ["asc", "desc"]},
                    },
                    {
                        "name": "busca",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "maxLength": 5},
                    },
                ],
                "responses": {"200": {"description": "ok"}},
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
        if creds.get("username") == "alice" and creds.get("password") == PASSWORD:
            return Reply(200, json.dumps({"access_token": TOKEN}).encode())
        return Reply(401, b"{}")
    if r.headers.get("authorization") != f"Bearer {TOKEN}":
        return Reply(401, b"{}")
    if r.path == "/api/lista":
        return lista(r)
    return Reply(200, b'{"ok":true}')


def lista(r: Received) -> Reply:
    mode = MODE["lista"]
    query = dict(parse_qsl(urlsplit(r.target).query, keep_blank_values=True))
    limit = query.get("limite", "")
    valid = (
        limit.isdigit()
        and 1 <= int(limit) <= 100
        and query.get("ordem") in {"asc", "desc"}
        and len(query.get("busca", "x" * 9)) <= 5
    )
    if mode == "down":
        return Reply(503, b"{}")
    if valid or mode == "lax":
        return Reply(200, b'{"items":[]}')
    return Reply(500, b"{}") if mode == "crash" else Reply(400, b"{}")


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
    monkeypatch.setenv("CONTRATO_A_SENHA", PASSWORD)
    MODE["lista"] = "validate"


def profile_data(server: LocalServer, **negative: Any) -> dict[str, Any]:
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
            "alias": "user_a",
            "role": "usuario",
            "username": {"secret_ref": "env:CONTRATO_A_LOGIN"},
            "password": {"secret_ref": "env:CONTRATO_A_SENHA"},
        }
    ]
    data["probe"] = {"health_path": "/api/saude"}
    if negative:
        data["negative"] = negative
    return data


def write_product(products: Path, data: dict[str, Any]) -> None:
    folder = products / "demo"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "target.yml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (folder / "openapi.yml").write_text(yaml.safe_dump(OPENAPI), encoding="utf-8")
    approve_product_on_disk(products, "demo")  # o que uma pessoa faria no terminal


@contextmanager
def environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **negative: Any
) -> Iterator[tuple[LocalServer, Path]]:
    products = tmp_path / "produtos"
    products.mkdir(exist_ok=True)
    with serve(handler) as server:
        write_product(products, profile_data(server, **negative))
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


NEGATIVE_KEYS = {
    "schema_version",
    "run_id",
    "product",
    "dry_run",
    "status",
    "stop_message",
    "started_at",
    "finished_at",
    "requests_sent",
    "accounts",
    "created_resources",
    "restored_resources",
    "by_class",
    "operations",
    "operations_tested",
    "plan",
    "findings",
    "not_tested",
    "limits",
    "notice",
}


def run_negative(
    capsys: pytest.CaptureFixture[str], products: Path, run_id: str, *extra: str
) -> tuple[int, dict[str, Any], str]:
    return invoke_json(
        capsys, "negative", "demo", "--run", run_id, "--products-dir", str(products), *extra
    )


def test_a_server_that_validates_gives_exit_0_without_findings_and_writes_negative_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, err = run_negative(capsys, products, run_id)

    assert code == ExitCode.OK
    assert set(envelope) == {"schema_version", "ok", "run_id", "data"}
    assert envelope["ok"] is True
    assert envelope["run_id"] == run_id
    data = envelope["data"]
    assert set(data) == NEGATIVE_KEYS
    assert data["status"] == "completed"
    assert data["findings"] == []
    assert data["requests_sent"] >= 1
    assert data["operations_tested"] == 1
    assert sum(row["rejected"] for row in data["by_class"]) == data["requests_sent"]
    on_disk = json.loads((tmp_path / "runs" / run_id / "negative.json").read_text("utf-8"))
    assert on_disk == data
    everything = json.dumps(envelope) + err + json.dumps(on_disk)
    for secret in (PASSWORD, TOKEN, ZAP_KEY):
        assert secret not in everything
    assert "not-a-number" not in everything


def test_a_finding_is_data_and_never_a_failing_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    MODE["lista"] = "lax"
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, _ = run_negative(capsys, products, run_id)

    assert code == ExitCode.OK
    findings = envelope["data"]["findings"]
    assert {f["technique"] for f in findings} == {"input_accepted"}
    assert {f["origin"] for f in findings} == {"negative"}
    assert {f["field"] for f in findings} == {"limite", "ordem", "busca"}
    assert {f["status"] for f in findings} == {"needs_triage"}
    assert "not-a-number" not in json.dumps(envelope)


def test_a_crashing_server_is_a_server_error_finding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    MODE["lista"] = "crash"
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        code, envelope, _ = run_negative(capsys, products, run_id)

    assert code == ExitCode.OK
    assert {f["technique"] for f in envelope["data"]["findings"]} == {"input_server_error"}


def test_the_audit_lines_carry_the_negative_operation_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        run_negative(capsys, products, run_id)

    lines = (tmp_path / "runs" / run_id / "audit.jsonl").read_text("utf-8").splitlines()
    entries = [json.loads(line) for line in lines]
    assert any(e["operation_id"] == "negative:lista" for e in entries)
    seqs = [e["seq"] for e in entries if e["phase"] == "decision"]
    assert len(seqs) == len(set(seqs))


def test_dry_run_plans_without_sending_or_writing_and_without_the_stack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        run_id = probe(capsys, products)
        before = len(server.requests)
        code, envelope, _ = run_negative(capsys, products, run_id, "--dry-run")
        after = len(server.requests)

    assert code == ExitCode.OK
    assert "run_id" not in envelope
    data = envelope["data"]
    assert data["dry_run"] is True
    assert data["requests_sent"] == 0
    assert before == after
    assert {case["operation_id"] for case in data["plan"]} == {"lista"}
    assert {case["method"] for case in data["plan"]} == {"GET"}
    assert not (tmp_path / "runs" / run_id / "negative.json").exists()


def test_the_human_output_is_a_portuguese_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    MODE["lista"] = "lax"
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        code, out, _ = invoke(
            capsys, "negative", "demo", "--run", run_id, "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert "Negative de demo" in out
    assert "ACHADO" in out
    assert "input_accepted" in out


def test_the_max_requests_flag_only_lowers_the_profile_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path, max_requests=5) as (server, products):
        run_id = probe(capsys, products)
        sent = len(server.requests)
        code, envelope, _ = run_negative(capsys, products, run_id, "--max-requests", "6")
        assert len(server.requests) == sent
        ok_code, ok, _ = run_negative(capsys, products, run_id, "--max-requests", "2")

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert ok_code == ExitCode.OK
    assert ok["data"]["requests_sent"] == 2


@pytest.mark.parametrize(
    "extra",
    [["--only", "inventada"], ["--run", "../fora"], ["--run", "2026-01-01T00-00-00Z-demo-abcd"]],
)
def test_bad_arguments_are_a_usage_error_and_send_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        run_id = probe(capsys, products)
        sent = len(server.requests)
        args = ["negative", "demo", "--run", run_id, "--products-dir", str(products)]
        if extra[0] == "--run":
            args[3] = extra[1]
        else:
            args += extra
        code, envelope, _ = invoke_json(capsys, *args)
        assert len(server.requests) == sent

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"


def test_an_unapproved_profile_is_refused_before_any_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        run_id = probe(capsys, products)
        data = yaml.safe_load((products / "demo" / "target.yml").read_text("utf-8"))
        data["negative"] = {"allow_writes": True}  # liga a escrita depois da aprovação
        (products / "demo" / "target.yml").write_text(yaml.safe_dump(data), encoding="utf-8")
        sent = len(server.requests)
        code, envelope, _ = run_negative(capsys, products, run_id)
        dry_code, dry, _ = run_negative(capsys, products, run_id, "--dry-run")
        assert len(server.requests) == sent

    assert code == ExitCode.SCOPE
    assert envelope["error"]["code"] == "SCOPE_NOT_APPROVED"
    assert (dry_code, dry["error"]["code"]) == (ExitCode.SCOPE, "SCOPE_NOT_APPROVED")


def test_an_expired_authorization_is_exit_3(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        run_id = probe(capsys, products)
        data = profile_data(server)
        data["scope"]["authorization"]["valid_until"] = "2020-01-01"
        write_product(products, data)
        sent = len(server.requests)
        code, envelope, _ = run_negative(capsys, products, run_id)
        assert len(server.requests) == sent

    assert code == ExitCode.SCOPE
    assert envelope["ok"] is False


def test_a_target_that_stops_answering_is_exit_6_with_the_partial_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        MODE["lista"] = "down"
        code, envelope, _ = run_negative(capsys, products, run_id)

    assert code == ExitCode.TARGET
    assert envelope["ok"] is False
    assert envelope["data"]["status"] == "stopped_target_unresponsive"
    assert envelope["run_id"] == run_id


def test_without_the_probe_exchanges_the_command_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        run_id = probe(capsys, products)
        (tmp_path / "runs" / run_id / "exchanges.json").unlink()
        code, envelope, _ = run_negative(capsys, products, run_id)

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
