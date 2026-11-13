"""`stack up`, `preflight` e `probe` contra o VAmPI real, com o ZAP 2.17 e o proxy de escopo reais.

Mede a alcançabilidade que o spike do M0 anotou à mão (14 de 14 operações, com `DELETE` por
administrador) e confere o resto da cadeia: as requisições estão no histórico do ZAP dentro do
contexto da execução, a trilha do proxy e a da CLI concordam, nada saiu do escopo, e a parada
de emergência derruba a saída. Exige Docker; pulado quando ele não responde.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from tests.integration.lab_support import (
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    CliResult,
    LabCli,
    ZapView,
    manifest,
    proxy_audit,
    request_line,
    require_docker,
    run_audit,
    target_zap_requests,
)

pytestmark = pytest.mark.integration

# Usuários que o GET /createdb semeia (README do VAmPI): dados públicos do alvo de treino, não
# segredos. O VAmPI não permite escolher a senha, então não há credencial a gerar.
SEEDED = {
    "VAMPI_USER_A_USERNAME": "name1",
    "VAMPI_USER_A_PASSWORD": "pass1",
    "VAMPI_USER_B_USERNAME": "name2",
    "VAMPI_USER_B_PASSWORD": "pass2",
    "VAMPI_ADMIN_USERNAME": "admin",
    "VAMPI_ADMIN_PASSWORD": "pass1",
}
OPERATIONS = 14


@dataclass(frozen=True)
class VampiRun:
    """O que a sequência `stack up` -> `preflight` -> `probe` produziu."""

    cli: LabCli
    preflight: CliResult
    probe: CliResult
    window: tuple[str, str]


def _start(root: Path) -> LabCli:
    cli = LabCli(root, SEEDED)
    cli.install_product("vampi", VAMPI_PROFILE, (VAMPI_OPENAPI,))
    up = cli.run("stack", "up", "vampi", timeout=420)
    assert up.code == 0, up.stdout + up.stderr
    return cli


@pytest.fixture(scope="module")
def vampi_run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[VampiRun]:
    require_docker()
    cli = _start(tmp_path_factory.mktemp("vampi"))
    try:
        preflight = cli.run("preflight", "vampi")
        probe = cli.run("probe", "vampi", "--include-delete")
        started = str(probe.data.get("started_at", ""))
        finished = str(probe.data.get("finished_at", ""))
        yield VampiRun(cli, preflight, probe, (started, finished))
    finally:
        cli.stack_down()


def test_preflight_is_ready_with_the_real_zap_and_proxy(vampi_run: VampiRun) -> None:
    result = vampi_run.preflight

    assert result.code == 0, result.stdout
    assert result.data["ready"] is True
    assert {c["id"] for c in result.data["checks"] if c["ok"]} >= {
        "zap",
        "target_health",
        "login:user_a",
        "login:user_b",
        "login:admin_a",
    }
    assert re.match(r"2\.17\.", result.data["zap_version"])


def test_probe_reaches_all_fourteen_operations_like_the_handcrafted_baseline(
    vampi_run: VampiRun,
) -> None:
    probe = vampi_run.probe

    assert probe.code == 0, probe.stdout
    summary = probe.data["summary"]
    assert probe.data["status"] == "completed"
    assert summary["operations_total"] == OPERATIONS
    assert summary["successes"] == OPERATIONS
    assert summary["reachability"] == 1.0
    assert summary["reachability_all"] == 1.0
    assert summary["by_outcome"] == {"success": OPERATIONS}


def test_each_operation_used_the_account_the_profile_maps(vampi_run: VampiRun) -> None:
    accounts = {op["operation_id"]: op["account"] for op in vampi_run.probe.data["operations"]}

    assert accounts["api_views.users.update_email"] == "user_b"
    assert accounts["api_views.users.update_password"] == "user_b"  # noqa: S105 - id de operação
    assert accounts["api_views.users.delete_user"] == "admin_a"
    assert accounts["api_views.users.me"] == "user_a"


def test_every_zap_route_request_is_in_the_zap_history_inside_the_run_context(
    vampi_run: VampiRun,
) -> None:
    cli = vampi_run.cli
    run_id = vampi_run.probe.envelope["run_id"]
    sent = target_zap_requests(run_audit(cli, run_id))
    zap = ZapView(cli.state_file())
    context = f"hdast-{run_id}"

    messages = zap.proxied_messages("http://vampi:5000")
    includes, excludes = zap.context_regexes(context)

    assert context in zap.contexts()
    assert manifest(cli, run_id)["zap_context_id"] >= 1
    assert len(messages) == len(sent) == OPERATIONS
    assert sorted((m, urlpath(u)) for m, u in map(request_line, messages)) == sorted(sent)
    for message in messages:
        method, url = request_line(message)
        assert any(re.fullmatch(r, url) for r in includes), (method, url)
        assert not any(re.fullmatch(r, url) for r in excludes), (method, url)


def test_login_traffic_goes_through_the_auth_route_and_stays_out_of_the_zap_history(
    vampi_run: VampiRun,
) -> None:
    cli = vampi_run.cli
    run_id = vampi_run.probe.envelope["run_id"]
    logins = [
        row
        for row in run_audit(cli, run_id)
        if row["phase"] == "decision" and row["operation_id"] == "auth.login"
    ]
    zap = ZapView(cli.state_file())

    urls = [request_line(m)[1] for m in zap.proxied_messages("http://vampi:5000")]

    assert sorted(row["account"] for row in logins) == ["admin_a", "user_a", "user_b"]
    assert {row["route"] for row in logins} == {"auth"}
    # Só a operação de login do OpenAPI (dados de regra, rota do ZAP) aparece no histórico do ZAP.
    assert [u for u in urls if u.endswith("/users/v1/login")] == [
        "http://vampi:5000/users/v1/login"
    ]


def test_proxy_audit_and_cli_audit_agree_and_nothing_left_the_scope(vampi_run: VampiRun) -> None:
    cli = vampi_run.cli
    run_id = vampi_run.probe.envelope["run_id"]
    start, end = (datetime.fromisoformat(stamp) for stamp in vampi_run.window)
    cli_allowed = sorted(
        (row["method"], row["path"])
        for row in run_audit(cli, run_id)
        if row["phase"] == "decision" and row["decision"] == "allowed"
    )

    proxy_rows = [r for r in proxy_audit(cli) if start <= datetime.fromisoformat(r["ts"]) <= end]

    assert proxy_rows, "a trilha do proxy não registrou a execução"
    assert (
        sorted((r["method"], r["path"]) for r in proxy_rows if r["decision"] == "allow")
        == cli_allowed
    )
    assert [r for r in proxy_audit(cli) if r["decision"] == "deny"] == []
    assert {(r["host"], r["port"]) for r in proxy_audit(cli)} == {("vampi", 5000)}


def test_a_second_probe_in_the_same_stack_also_completes(vampi_run: VampiRun) -> None:
    cli = vampi_run.cli
    cli.run("preflight", "vampi")  # repopula o banco (health_path: /createdb) e prova os logins

    again = cli.run("probe", "vampi", "--include-delete")

    assert again.code == 0, again.stdout
    assert again.data["summary"]["successes"] == OPERATIONS


@pytest.fixture
def killable_stack(tmp_path: Path) -> Iterator[LabCli]:
    require_docker()
    cli = _start(tmp_path)
    try:
        yield cli
    finally:
        cli.stack_down()


def test_stop_makes_subsequent_requests_fail_fast_and_is_audited(killable_stack: LabCli) -> None:
    cli = killable_stack
    assert cli.run("preflight", "vampi").code == 0
    before = len(proxy_audit(cli))

    stopped = cli.run("stop")
    after = cli.run("preflight", "vampi", timeout=120)

    assert stopped.code == 0, stopped.stdout
    assert stopped.data["kill_created"] is True
    assert after.code != 0
    assert after.data["ready"] is False
    # O `RunGate` da CLI já consulta a trava: nada chega ao proxy depois do `stop`. Se algo chegou
    # (corrida entre o `stop` e a consulta), o proxy negou por `kill_switch`.
    rows = proxy_audit(cli)[before:]
    assert [r for r in rows if r["decision"] == "allow"] == []
    assert {r["reason"] for r in rows if r["decision"] == "deny"} <= {"kill_switch"}
    assert "trava de emergência" in after.stdout


def urlpath(url: str) -> str:
    """Caminho (sem consulta) de uma URL absoluta."""
    return re.sub(r"^https?://[^/]+", "", url).split("?")[0] or "/"
