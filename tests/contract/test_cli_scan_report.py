"""Contrato de `hdast scan` e `hdast report`: envelope, códigos de saída e arquivos da execução.

Um servidor HTTP real em 127.0.0.1 faz de API do ZAP (inclusive a de varredura), de proxy e de
alvo. O `probe` roda de verdade pela CLI antes; relógio e espera do `scan` são trocados por um
relógio manual na montagem da CLI para a janela poder fechar no meio sem esperar.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from harness_dast.cli import scan_composition
from harness_dast.domain.errors import ExitCode
from tests.contract.test_cli_probe_commands import (
    LOGIN,
    PASSWORD,
    TOKEN,
    ZAP_KEY,
    _env,  # noqa: F401 - fixture autouse do módulo do probe
    environment,
    invoke,
    invoke_json,
    write_product,
)
from tests.contract.test_cli_probe_commands import target_handler as probe_target_handler
from tests.fakes.local_server import LocalServer, Received, Reply
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.runtime import ManualClock
from tests.fakes.zap_scan_server import FakeScanZapServer

pytestmark = pytest.mark.contract

ATTACK_ID = "1604"


class Combined:
    """Alvo, proxy e API do ZAP (probe e varredura) no mesmo servidor."""

    def __init__(self) -> None:
        self.scan = FakeScanZapServer(
            api_key=ZAP_KEY,
            context_regex=r"^http://127\.0\.0\.1:\d+/.*",
            context_name="",
            context_id="1",
        )
        self.health_status = 200
        self.alert_risk = "High"
        self.raise_alerts = True

    def __call__(self, r: Received) -> Reply:
        if r.path.startswith("/JSON/"):
            return self._zap(r)
        if r.path == "/api/saude" and self.health_status != 200:
            return Reply(self.health_status, b"{}")
        reply = probe_target_handler(r)
        if r.is_absolute:
            self.scan.messages.append(self._learned(r, reply))
        return reply

    def _zap(self, r: Received) -> Reply:
        scan_routes = (
            "/JSON/ascan/",
            "/JSON/alert/",
            "/JSON/replacer/action/",
            "/JSON/context/view/",
        )
        message_routes = ("/JSON/core/view/messages/", "/JSON/core/view/message/")
        if r.path.startswith(scan_routes + message_routes):
            reply = self.scan(r)
            if r.path == "/JSON/ascan/action/scan/" and reply.status == 200:
                self._raise_alert()
            return reply
        return probe_target_handler(r)

    def _learned(self, r: Received, reply: Reply) -> dict[str, str]:
        headers = "".join(f"{k}: {v}\r\n" for k, v in r.headers.items())
        return {
            "id": str(len(self.scan.messages) + 1),
            "type": "1",
            "requestHeader": f"{r.method} {r.target} HTTP/1.1\r\n{headers}",
            "requestBody": r.body.decode(),
            "responseHeader": f"HTTP/1.1 {reply.status} OK\r\n",
            "responseBody": "{}",
        }

    def _raise_alert(self) -> None:
        learned = [m for m in self.scan.messages if "/api/ler" in m["requestHeader"]]
        if self.raise_alerts and learned and not self.scan.alerts:
            self.scan.alerts.append(
                {
                    "id": "1",
                    "pluginId": "40018",
                    "alertRef": "40018",
                    "alert": "SQL Injection",
                    "cweid": "89",
                    "wascid": "19",
                    "risk": self.alert_risk,
                    "confidence": "Low",
                    "method": "GET",
                    "url": f"http://127.0.0.1/api/ler/'?token={TOKEN}",
                    "attack": "'",
                    "evidence": f"Authorization: Bearer {TOKEN}",
                    "inputVector": "urlpath",
                    "messageId": ATTACK_ID,
                    "sourceMessageId": learned[0]["id"],
                }
            )
            self.scan.messages.append(
                {
                    "id": ATTACK_ID,
                    "type": "3",
                    "requestHeader": (
                        "GET http://127.0.0.1/api/ler/' HTTP/1.1\r\n"
                        f"Authorization: Bearer {TOKEN}\r\n"
                    ),
                    "requestBody": json.dumps({"password": PASSWORD, "login": LOGIN}),
                    "responseHeader": "HTTP/1.1 500 Internal Server Error\r\n",
                    "responseBody": f'{{"erro": "falha", "access_token": "{TOKEN}"}}',
                }
            )


def scan_args(run_id: str, products: Path, *extra: str) -> list[str]:
    return ["scan", "demo", "--run", run_id, "--products-dir", str(products), *extra]


def probe_then(
    capsys: pytest.CaptureFixture[str], products: Path, server: LocalServer, combined: Combined
) -> str:
    combined.scan.context_name = ""
    code, envelope, _ = invoke_json(capsys, "probe", "demo", "--products-dir", str(products))
    assert code == ExitCode.OK
    run_id: str = envelope["run_id"]
    combined.scan.context_name = f"hdast-{run_id}"
    return run_id


def files_text(run_dir: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in run_dir.iterdir() if p.is_file())


def assert_clean(*texts: str) -> None:
    for text in texts:
        for secret in (PASSWORD, TOKEN, ZAP_KEY):
            assert secret not in text


def manual_clock(monkeypatch: pytest.MonkeyPatch) -> ManualClock:
    clock = ManualClock()
    for module in (scan_composition,):
        monkeypatch.setattr(module, "SystemClock", lambda: clock)
        monkeypatch.setattr(module, "SystemSleeper", lambda: clock)
    return clock


def test_scan_runs_the_learned_requests_and_stores_redacted_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    manual_clock(monkeypatch)
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        code, envelope, err = invoke_json(capsys, *scan_args(run_id, products))

    assert code == ExitCode.OK
    assert set(envelope) == {"schema_version", "ok", "run_id", "data"}
    assert envelope["run_id"] == run_id
    data = envelope["data"]
    assert {
        "status",
        "policy",
        "limits",
        "planned",
        "entries",
        "skipped",
        "learned",
        "alerts_total",
        "alerts_by_risk",
        "evidence_messages",
        "health",
        "rules_removed",
        "notice",
    } <= set(data)
    assert data["status"] == "completed"
    assert [e["operation_id"] for e in data["entries"]] == ["ler", "gravar"]
    assert data["limits"]["threads_per_host"] == 2
    assert data["policy"]["url_path_injection"] is True
    assert data["alerts_total"] == 1
    assert data["rules_removed"] is True
    run_dir = tmp_path / "runs" / run_id
    for name in ("scan.json", "scan-progress.json", "alerts.raw.json", "evidence.json"):
        assert (run_dir / name).is_file()
    assert combined.scan.rules == {}
    started = [q for name, q in combined.scan.calls if name == "ascan/action/scan"]
    assert all(q["contextId"] == "1" for q in started)
    assert_clean(json.dumps(envelope), err, files_text(run_dir))


def test_scan_dry_run_shows_the_plan_without_touching_zap_target_or_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        before = (len(server.requests), len(combined.scan.calls))
        code, envelope, _ = invoke_json(capsys, *scan_args(run_id, products, "--dry-run"))
        after = (len(server.requests), len(combined.scan.calls))

    assert code == ExitCode.OK
    assert "run_id" not in envelope
    assert envelope["data"]["dry_run"] is True
    assert [p["operation_id"] for p in envelope["data"]["planned"]] == ["ler", "gravar"]
    assert before == after
    assert not (tmp_path / "runs" / run_id / "scan.json").exists()


def test_scan_errors_are_usage_errors_with_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        bad_id, bad_envelope, _ = invoke_json(capsys, *scan_args("../x", products))
        missing, _, _ = invoke_json(capsys, *scan_args("2026-11-01T00-00-00Z-demo-aaaa", products))
        outcome, _, _ = invoke_json(
            capsys, *scan_args(run_id, products, "--include-outcome", "server_error")
        )
        raised, _, _ = invoke_json(capsys, *scan_args(run_id, products, "--threads", "9"))
        no_run, _, _ = invoke_json(capsys, "scan", "demo", "--products-dir", str(products))

    assert bad_id == missing == outcome == raised == no_run == ExitCode.USAGE
    assert bad_envelope["error"]["code"] == "CONFIG_ERROR"


def test_scan_without_the_zap_context_exits_4(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        combined.scan.context_name = "outra-sessao"
        code, envelope, _ = invoke_json(capsys, *scan_args(run_id, products))

    assert code == ExitCode.PREFLIGHT
    assert envelope["error"]["code"] == "PREFLIGHT_FAILED"
    assert combined.scan.rules == {}


def test_window_closing_mid_scan_exits_3_with_partial_results_in_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    combined.scan.scan_states = [{"id": "0", "progress": "10", "state": "RUNNING"}]
    clock = manual_clock(monkeypatch)
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        scope = valid_profile_data("demo")["scope"]
        scope["windows"] = ["seg-dom 00:00-12:01 UTC"]
        scope["allow"] = [
            {
                "host": "127.0.0.1",
                "scheme": "http",
                "port": server.port,
                "paths": ["/api/**"],
                "methods": ["GET", "POST"],
                "allow_local": True,
            }
        ]
        write_product(products, server, scope=scope)
        code, envelope, _ = invoke_json(capsys, *scan_args(run_id, products))

    assert code == ExitCode.SCOPE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "SCOPE_VIOLATION"
    assert envelope["data"]["status"] == "stopped_window"
    assert envelope["data"]["entries"][0]["outcome"] == "stopped"
    assert (tmp_path / "runs" / run_id / "scan.json").is_file()
    assert combined.scan.rules == {}
    assert clock.now().minute >= 1


def test_zap_failure_mid_scan_exits_5(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    manual_clock(monkeypatch)
    original = combined.scan._ascan_view_scans
    combined.scan._ascan_view_scans = lambda query: Reply(200, b"nao e json")  # type: ignore[method-assign]
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        code, envelope, _ = invoke_json(capsys, *scan_args(run_id, products))
    combined.scan._ascan_view_scans = original  # type: ignore[method-assign]

    assert code == ExitCode.EXTERNAL_TOOL
    assert envelope["error"]["code"] == "EXTERNAL_TOOL_ERROR"
    assert envelope["data"]["status"] == "stopped_zap"
    assert combined.scan.rules == {}


def test_unresponsive_target_exits_6(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    manual_clock(monkeypatch)
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        combined.health_status = 503
        code, envelope, _ = invoke_json(capsys, *scan_args(run_id, products))

    assert code == ExitCode.TARGET
    assert envelope["error"]["code"] == "TARGET_ERROR"
    assert envelope["data"]["status"] == "stopped_target_unresponsive"
    assert envelope["data"]["entries"] == []
    assert combined.scan.rules == {}


def scanned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    combined: Combined,
    **profile: Any,
) -> tuple[str, Path]:
    manual_clock(monkeypatch)
    with environment(monkeypatch, tmp_path, combined, **profile) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        code, _, _ = invoke_json(capsys, *scan_args(run_id, products))
        assert code == ExitCode.OK
        return run_id, products


def test_report_writes_findings_and_markdown_and_exits_zero_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        manual_clock(monkeypatch)
        run_id = probe_then(capsys, products, server, combined)
        invoke_json(capsys, *scan_args(run_id, products))
        code, envelope, err = invoke_json(
            capsys, "report", "demo", "--run", run_id, "--products-dir", str(products)
        )
        requests_after = len(server.requests)

    assert code == ExitCode.OK
    assert set(envelope) == {"schema_version", "ok", "run_id", "data"}
    data = envelope["data"]
    assert {
        "files",
        "threshold",
        "exceeds_threshold",
        "summary",
        "coverage",
        "not_tested_statements",
        "findings",
        "not_observed",
    } <= set(data)
    assert data["files"] == ["findings.json", "report.md", "report.html"]
    assert [g["findings_count"] for g in data["groups"]] == [1]
    assert data["exceeds_threshold"] is False
    # ADR 0049: campos aditivos; sem pilha gerenciada a cerca não registrou nada desta execução.
    assert data["proxy_signals"]["enabled"] is False
    assert data["proxy_signals"]["findings"] == []
    assert data["summary"]["signal_by_severity"] == {}
    (finding,) = data["findings"]
    assert finding["operation_id"] == "ler"
    assert finding["proposed_severity"] == "high"
    run_dir = tmp_path / "runs" / run_id
    assert not (run_dir / "error-signals.json").exists()
    saved = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
    assert saved["proxy_signals"]["enabled"] is False
    assert (run_dir / "findings.json").is_file()
    assert (run_dir / "report.md").is_file()
    assert (run_dir / "report.html").is_file()
    assert_clean(json.dumps(envelope), err, files_text(run_dir))
    assert requests_after == len(server.requests)


def test_report_fail_on_exits_1_as_a_result_not_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        manual_clock(monkeypatch)
        run_id = probe_then(capsys, products, server, combined)
        invoke_json(capsys, *scan_args(run_id, products))
        base = ["report", "demo", "--run", run_id, "--products-dir", str(products)]
        flagged, envelope, _ = invoke_json(capsys, *base, "--fail-on", "high")
        clean, _, _ = invoke_json(capsys, *base, "--fail-on", "none")
        invalid, bad, _ = invoke_json(capsys, *base, "--fail-on", "critico")

    assert flagged == ExitCode.FINDINGS
    assert int(flagged) == 1
    assert envelope["ok"] is True
    assert envelope["data"]["exceeds_threshold"] is True
    assert clean == ExitCode.OK
    assert invalid == ExitCode.USAGE
    assert bad["error"]["code"] == "CONFIG_ERROR"


def test_report_errors_are_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        run_id = probe_then(capsys, products, server, combined)
        base = ["--products-dir", str(products)]
        without_scan, envelope, _ = invoke_json(capsys, "report", "demo", "--run", run_id, *base)
        bad_id, _, _ = invoke_json(capsys, "report", "demo", "--run", "../x", *base)

    assert without_scan == bad_id == ExitCode.USAGE
    assert "scan.json" in envelope["error"]["message"]


def test_report_compare_marks_findings_and_says_not_observed_never_fixed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        manual_clock(monkeypatch)
        first = probe_then(capsys, products, server, combined)
        invoke_json(capsys, *scan_args(first, products))
        invoke_json(capsys, "report", "demo", "--run", first, "--products-dir", str(products))
        combined.scan.alerts.clear()
        combined.scan.messages.clear()
        combined.raise_alerts = False
        second = probe_then(capsys, products, server, combined)
        invoke_json(capsys, *scan_args(second, products))
        code, envelope, _ = invoke_json(
            capsys,
            "report",
            "demo",
            "--run",
            second,
            "--compare",
            first,
            "--products-dir",
            str(products),
        )
        human_code, out, _ = invoke(
            capsys,
            "report",
            "demo",
            "--run",
            second,
            "--compare",
            first,
            "--products-dir",
            str(products),
        )

    assert code == human_code == ExitCode.OK
    data = envelope["data"]
    assert data["comparison"]["baseline_run_id"] == first
    assert data["comparison"]["not_observed"] == 1
    assert data["comparison"]["persistent"] == 0
    assert data["findings"] == []
    assert data["not_observed"][0]["operation_scanned_now"] is True
    assert "não observados 1" in out
    assert "não observado não é corrigido" in out


def test_report_human_output_is_portuguese_and_warns_it_is_not_proof_of_security(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    combined = Combined()
    with environment(monkeypatch, tmp_path, combined) as (server, products):
        manual_clock(monkeypatch)
        run_id = probe_then(capsys, products, server, combined)
        invoke_json(capsys, *scan_args(run_id, products))
        code, out, _ = invoke(
            capsys, "report", "demo", "--run", run_id, "--products-dir", str(products)
        )

    assert code == ExitCode.OK
    assert "Relatório de demo" in out
    assert "não prova segurança" in out
