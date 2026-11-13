"""Contrato de `hdast spec inspect`, `hdast preflight` e `hdast probe`: envelope e códigos de saída.

Um servidor HTTP real em 127.0.0.1 faz de API do ZAP, de proxy e de alvo ao mesmo tempo. O
relógio e a espera são trocados por falsos na montagem da CLI, para a janela poder fechar no
meio da execução sem esperar de verdade.
"""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness_dast.cli import composition
from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode
from tests.fakes.local_server import LocalServer, Received, Reply, free_port, serve
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.runtime import ManualClock

pytestmark = pytest.mark.contract

PASSWORD = "SenhaDoContrato-777"  # noqa: S105 - sentinela ou nome de campo, não um segredo
LOGIN = "usuario-contrato"
TOKEN = "tok-DO-CONTRATO-123456"  # noqa: S105 - sentinela ou nome de campo, não um segredo
ZAP_KEY = "chave-zap-do-contrato-9"

OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Contrato", "version": "1"},
    "paths": {
        "/api/ler": {"get": {"operationId": "ler", "responses": {"200": {"description": "ok"}}}},
        "/api/gravar": {
            "post": {
                "operationId": "gravar",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["nome"],
                                "properties": {"nome": {"type": "string"}},
                            }
                        }
                    },
                },
                "responses": {"200": {"description": "ok"}},
            }
        },
        "/api/admin/x": {
            "get": {"operationId": "admin", "responses": {"200": {"description": "ok"}}}
        },
    },
}
PROBE_KEYS = {"run_id", "product", "dry_run", "status", "seed", "summary", "operations", "notice"}


def target_handler(r: Received) -> Reply:
    if r.path.startswith("/JSON/"):
        if r.headers.get("x-zap-api-key") != ZAP_KEY:
            return Reply(400, b'{"code":"bad_api_key"}')
        payloads = {
            "/JSON/core/view/version/": {"version": "2.17.0"},
            "/JSON/context/action/newContext/": {"contextId": "1"},
            "/JSON/replacer/view/rules/": {"rules": []},
        }
        return Reply(200, json.dumps(payloads.get(r.path, {"Result": "OK"})).encode())
    if r.path == "/api/auth/login":
        creds = json.loads(r.body or b"{}")
        if creds == {"username": LOGIN, "password": PASSWORD}:
            return Reply(200, json.dumps({"access_token": TOKEN}).encode())
        return Reply(401, b"{}")
    if r.headers.get("authorization") != f"Bearer {TOKEN}" and r.path != "/api/saude":
        return Reply(401, b"{}")
    return Reply(200, b'{"ok":true}')


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in (
        "HDAST_ZAP_BASE_URL",
        "HDAST_ZAP_API_KEY",
        "HDAST_ZAP_PROXY_URL",
        "HDAST_AUTH_PROXY_URL",
        "HDAST_PRODUCTS_DIR",
        "HDAST_LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HDAST_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("HDAST_ZAP_API_KEY", ZAP_KEY)
    monkeypatch.setenv("CONTRATO_LOGIN", LOGIN)
    monkeypatch.setenv("CONTRATO_SENHA", PASSWORD)


def write_product(products: Path, server: LocalServer, **profile_changes: Any) -> None:
    data = valid_profile_data("demo")
    data["environment"]["base_url"] = server.base_url
    data["openapi"] = "./openapi.yml"
    data["scope"]["allow"] = [
        {
            "host": "127.0.0.1",
            "scheme": "http",
            "port": server.port,
            "paths": ["/api/**"],
            "methods": ["GET", "POST"],
            "allow_local": True,
        }
    ]
    data["auth"]["accounts"][0]["username"] = {"secret_ref": "env:CONTRATO_LOGIN"}
    data["auth"]["accounts"][0]["password"] = {"secret_ref": "env:CONTRATO_SENHA"}
    data["auth"]["token_response_field"] = "access_token"  # noqa: S105 - sentinela ou nome de campo, não um segredo
    data["auth"]["token_path"] = "/api/auth/login"  # noqa: S105 - sentinela ou nome de campo, não um segredo
    data["probe"] = {"health_path": "/api/saude"}
    data.update(profile_changes)
    folder = products / "demo"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "target.yml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (folder / "openapi.yml").write_text(yaml.safe_dump(OPENAPI), encoding="utf-8")


@contextmanager
def environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    handler: Any = target_handler,
    **profile_changes: Any,
) -> Iterator[tuple[LocalServer, Path]]:
    products = tmp_path / "produtos"
    products.mkdir(exist_ok=True)
    with serve(handler) as server:
        write_product(products, server, **profile_changes)
        monkeypatch.setenv("HDAST_ZAP_BASE_URL", server.base_url)
        yield server, products


def invoke(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = run_app(build_app(), list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def invoke_json(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any], str]:
    code, out, err = invoke(capsys, "--json", *args)
    return code, json.loads(out), err


def assert_no_secrets(*texts: str) -> None:
    for text in texts:
        for secret in (PASSWORD, TOKEN, ZAP_KEY):
            assert secret not in text


# ------------------------------------------------------------ spec inspect


def test_spec_inspect_returns_the_summary_and_the_cross_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        code, envelope, _ = invoke_json(
            capsys, "spec", "inspect", "demo", "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert set(envelope) == {"schema_version", "ok", "data"}
    data = envelope["data"]
    assert {
        "product",
        "summary",
        "servers_out_of_scope",
        "not_sent",
        "suspicious_operations",
        "data_rules",
        "flows",
        "unused_rules",
        "needs_rule",
        "needs_rule_unchecked",
        "issues",
    } == set(data)
    assert data["summary"]["operation_count"] == 3
    assert [n["operation_id"] for n in data["not_sent"]] == ["admin"]
    assert data["not_sent"][0]["reason"] == "skipped_denied"
    assert server.requests == []  # spec inspect nunca toca a rede


def test_spec_inspect_budget_is_bounded_by_the_domain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        low, env_low, _ = invoke_json(
            capsys, "spec", "inspect", "demo", "--budget", "10", "--products-dir", str(products)
        )
        high, _, _ = invoke_json(
            capsys,
            "spec",
            "inspect",
            "demo",
            "--budget",
            "99999999",
            "--products-dir",
            str(products),
        )
        ok, _, _ = invoke_json(
            capsys, "spec", "inspect", "demo", "--budget", "2000", "--products-dir", str(products)
        )

    assert (low, high, ok) == (ExitCode.USAGE, ExitCode.USAGE, ExitCode.OK)
    assert env_low["error"]["code"] == "CONFIG_ERROR"


def test_spec_inspect_human_output_is_a_portuguese_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        code, out, _ = invoke(capsys, "spec", "inspect", "demo", "--products-dir", str(products))

    assert code == ExitCode.OK
    assert "OpenAPI de demo" in out
    assert "nunca enviada" in out


def test_spec_inspect_of_an_unknown_product_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, _ = invoke_json(
        capsys, "spec", "inspect", "nada", "--products-dir", str(tmp_path)
    )

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"


# --------------------------------------------------------------- preflight


def test_preflight_ready_exits_zero_with_the_checklist_and_audit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        code, envelope, err = invoke_json(
            capsys, "preflight", "demo", "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert envelope["ok"] is True
    assert set(envelope) == {"schema_version", "ok", "run_id", "data"}
    data = envelope["data"]
    assert data["ready"] is True
    assert data["zap_version"] == "2.17.0"
    assert [c["id"] for c in data["checks"]] == [
        "authorization",
        "window",
        "secrets:user_a",
        "zap",
        "target_health",
        "login:user_a",
    ]
    assert all(set(c) == {"id", "ok", "detail", "kind"} for c in data["checks"])
    run_dir = tmp_path / "runs" / envelope["run_id"]
    assert (run_dir / "audit.jsonl").is_file()
    assert (run_dir / "manifest.json").is_file()
    assert_no_secrets(
        json.dumps(envelope), err, (run_dir / "audit.jsonl").read_text(encoding="utf-8")
    )


def test_preflight_with_a_missing_secret_exits_4_and_hides_the_variable_name_from_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CONTRATO_SENHA")
    with environment(monkeypatch, tmp_path) as (_, products):
        code, envelope, _ = invoke_json(
            capsys, "preflight", "demo", "--products-dir", str(products)
        )
        human_code, out, err = invoke(capsys, "preflight", "demo", "--products-dir", str(products))

    assert code == human_code == ExitCode.PREFLIGHT
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "PREFLIGHT_FAILED"
    assert envelope["data"]["ready"] is False
    assert "user_a.password" in json.dumps(envelope)
    assert "CONTRATO_SENHA" not in json.dumps(envelope)
    assert "CONTRATO_SENHA" in out  # a pessoa que opera vê o nome da variável
    assert "Erro [PREFLIGHT_FAILED]" in err


def test_preflight_outside_the_window_exits_3(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scope = valid_profile_data("demo")["scope"]
    scope["windows"] = ["seg-dom 00:00-00:01 UTC"]
    clock = ManualClock()
    monkeypatch.setattr(composition, "SystemClock", lambda: clock)
    with environment(monkeypatch, tmp_path) as (server, products):
        write_product(products, server, scope={**scope, "allow": _allow(server), "deny_paths": []})
        code, envelope, _ = invoke_json(
            capsys, "preflight", "demo", "--products-dir", str(products)
        )

    assert code == ExitCode.SCOPE
    assert envelope["error"]["code"] == "SCOPE_VIOLATION"
    assert envelope["data"]["ready"] is False
    assert server.requests == []


def _allow(server: LocalServer) -> list[dict[str, Any]]:
    return [
        {
            "host": "127.0.0.1",
            "scheme": "http",
            "port": server.port,
            "paths": ["/api/**"],
            "methods": ["GET", "POST"],
            "allow_local": True,
        }
    ]


# -------------------------------------------------------------------- probe


def test_probe_dry_run_sends_nothing_writes_nothing_and_reports_the_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        code, envelope, _ = invoke_json(
            capsys, "probe", "demo", "--dry-run", "--seed", "5", "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert set(envelope) == {"schema_version", "ok", "data"}
    data = envelope["data"]
    assert set(data) >= PROBE_KEYS
    assert data["dry_run"] is True
    assert data["seed"] == 5
    assert {o["operation_id"]: o["outcome"] for o in data["operations"]} == {
        "ler": "dry_run",
        "gravar": "dry_run",
        "admin": "skipped_denied",
    }
    assert server.requests == []
    assert not (tmp_path / "runs").exists()


def test_probe_runs_and_records_manifest_audit_and_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (server, products):
        code, envelope, err = invoke_json(
            capsys, "probe", "demo", "--seed", "9", "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert set(envelope) == {"schema_version", "ok", "run_id", "data"}
    data = envelope["data"]
    assert set(data) >= PROBE_KEYS
    assert data["status"] == "completed"
    assert data["summary"]["reachability"] == 1.0
    assert envelope["run_id"] == data["run_id"]
    run_dir = tmp_path / "runs" / envelope["run_id"]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["zap_version"] == "2.17.0"
    assert manifest["zap_context_id"] == 1
    assert manifest["seed"] == 9
    assert len(manifest["hashes"]["target_yml"]) == 64
    assert len(manifest["hashes"]["openapi"]) == 64
    assert manifest["hashes"]["flows"] is None
    audit = [
        json.loads(x) for x in (run_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {e["phase"] for e in audit} == {"decision", "result"}
    assert (
        json.loads((run_dir / "probe.json").read_text(encoding="utf-8"))["run_id"] == data["run_id"]
    )
    everything = "".join(p.read_text(encoding="utf-8") for p in run_dir.iterdir())
    assert_no_secrets(everything, json.dumps(envelope), err)
    proxied = [r for r in server.requests if r.is_absolute]
    assert {r.path for r in proxied} == {"/api/ler", "/api/gravar"}


def test_probe_only_runs_the_selected_operation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        code, envelope, _ = invoke_json(
            capsys, "probe", "demo", "--only", "ler", "--products-dir", str(products)
        )
        bad, bad_envelope, _ = invoke_json(
            capsys, "probe", "demo", "--only", "fantasma", "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert [o["operation_id"] for o in envelope["data"]["operations"]] == ["ler"]
    assert bad == ExitCode.USAGE
    assert bad_envelope["error"]["code"] == "CONFIG_ERROR"


def test_probe_without_zap_fails_at_start_with_exit_4(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        monkeypatch.setenv("HDAST_ZAP_BASE_URL", f"http://127.0.0.1:{free_port()}")
        code, envelope, _ = invoke_json(capsys, "probe", "demo", "--products-dir", str(products))

    assert code == ExitCode.PREFLIGHT
    assert envelope["error"]["code"] == "PREFLIGHT_FAILED"
    assert "data" not in envelope


def test_probe_with_a_wrong_password_fails_at_start_with_exit_4_without_leaking_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONTRATO_SENHA", "senha-errada-xyz-999")
    with environment(monkeypatch, tmp_path) as (_, products):
        code, envelope, err = invoke_json(capsys, "probe", "demo", "--products-dir", str(products))

    assert code == ExitCode.PREFLIGHT
    assert "senha-errada-xyz-999" not in json.dumps(envelope) + err


def test_probe_stops_with_exit_3_and_a_partial_result_when_the_window_closes_mid_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clock = ManualClock()
    monkeypatch.setattr(composition, "SystemClock", lambda: clock)
    monkeypatch.setattr(composition, "SystemSleeper", lambda: clock)

    def closing(r: Received) -> Reply:
        if r.path == "/api/admin/x":  # a primeira operação do plano (ordem alfabética do loader)
            clock.advance(31 * 60)
        return target_handler(r)

    scope = valid_profile_data("demo")["scope"]
    scope["windows"] = ["seg-dom 12:00-12:30 UTC"]
    with environment(monkeypatch, tmp_path, closing) as (server, products):
        write_product(products, server, scope={**scope, "allow": _allow(server), "deny_paths": []})
        code, envelope, _ = invoke_json(capsys, "probe", "demo", "--products-dir", str(products))

    assert code == ExitCode.SCOPE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "SCOPE_VIOLATION"
    assert envelope["data"]["status"] == "stopped_window"
    assert envelope["run_id"] == envelope["data"]["run_id"]
    run_dir = tmp_path / "runs" / envelope["run_id"]
    assert (
        json.loads((run_dir / "probe.json").read_text(encoding="utf-8"))["status"]
        == "stopped_window"
    )


def test_probe_stops_with_exit_5_when_the_zap_proxy_dies_mid_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        monkeypatch.setenv("HDAST_ZAP_PROXY_URL", f"http://127.0.0.1:{free_port()}")
        monkeypatch.setattr(composition, "REQUEST_TIMEOUT_SECONDS", 10.0)
        code, envelope, _ = invoke_json(capsys, "probe", "demo", "--products-dir", str(products))

    assert code == ExitCode.EXTERNAL_TOOL
    assert envelope["error"]["code"] == "EXTERNAL_TOOL_ERROR"
    assert envelope["data"]["status"] == "stopped_zap"


def test_probe_stops_with_exit_6_when_the_target_stops_answering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    openapi = {
        **OPENAPI,
        "paths": {
            f"/api/r{i}": {
                "get": {"operationId": f"r{i}", "responses": {"200": {"description": "ok"}}}
            }
            for i in range(8)
        },
    }

    def sluggish(r: Received) -> Reply:
        if r.path.startswith("/api/r"):
            return Reply(200, b"{}", delay=0.6)
        return target_handler(r)

    monkeypatch.setattr(composition, "REQUEST_TIMEOUT_SECONDS", 0.2)
    with environment(monkeypatch, tmp_path, sluggish) as (_, products):
        (products / "demo" / "openapi.yml").write_text(yaml.safe_dump(openapi), encoding="utf-8")
        code, envelope, _ = invoke_json(capsys, "probe", "demo", "--products-dir", str(products))

    assert code == ExitCode.TARGET
    assert envelope["error"]["code"] == "TARGET_ERROR"
    assert envelope["data"]["status"] == "stopped_target_unresponsive"
    assert [o["outcome"] for o in envelope["data"]["operations"]] == ["timeout"] * 5


def test_probe_human_output_lists_each_operation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with environment(monkeypatch, tmp_path) as (_, products):
        code, out, _ = invoke(capsys, "probe", "demo", "--dry-run", "--products-dir", str(products))

    assert code == ExitCode.OK
    assert "SIMULAÇÃO" in out
    assert "dry_run" in out
    assert "skipped_denied" in out


def test_environment_is_not_polluted_by_the_tests() -> None:
    assert os.environ.get("HDAST_ZAP_BASE_URL") is None
