"""`stack up` -> `preflight` -> `probe` contra a Clínica Piloto real (Spring Boot, JWT, XSRF).

Cobre o que o VAmPI não tem: login com limite de taxa, par XSRF nas escritas, encadeamento
de três níveis (convênio, paciente, consulta, receita), contas diferentes por operação,
códigos de erro do corpo, unicidade entre execuções seguidas e vencimento do token no meio
da execução. As credenciais são descartáveis, sorteadas aqui a cada subida. Exige Docker.
"""

import secrets
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import (
    PILOT_PROFILE,
    CliResult,
    LabCli,
    ZapView,
    pilot_state,
    proxy_audit,
    request_line,
    require_docker,
    run_audit,
)

pytestmark = pytest.mark.integration

PILOT_HOST = "http://clinica-piloto:8080"
FORBIDDEN = "/api/notificacoes/enviar"
CHAIN = ("criarConvenio", "criarMedico", "criarPaciente", "criarConsulta", "criarReceita")
CREATED_TABLES = ("convenio", "medico", "paciente", "consulta", "receita")
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LOGIN_PATH = "/api/auth/login"


def throwaway_credentials() -> dict[str, str]:
    """Contas e senhas descartáveis do alvo, novas a cada subida (nunca versionadas)."""
    env: dict[str, str] = {}
    for name in ("ADMIN", "MEDICO", "PACIENTE_A", "PACIENTE_B"):
        env[f"PILOT_{name}_USERNAME"] = f"it_{secrets.token_hex(4)}"
        env[f"PILOT_{name}_PASSWORD"] = secrets.token_urlsafe(18)
    return env


@dataclass(frozen=True)
class PilotRun:
    """Resultados de uma execução do `probe` e o estado do alvo logo depois."""

    result: CliResult
    zap_messages: list[dict[str, Any]]
    target: dict[str, Any]
    audit: list[dict[str, Any]]

    @property
    def operations(self) -> dict[str, dict[str, Any]]:
        """Resultado por `operation_id`."""
        return {op["operation_id"]: op for op in self.result.data["operations"]}

    @property
    def outcomes(self) -> Counter[str]:
        """Contagem por classe de resultado."""
        return Counter(op["outcome"] for op in self.result.data["operations"])


def _probe(cli: LabCli, *flags: str) -> PilotRun:
    result = cli.run("probe", "clinica-piloto", *flags)
    run_id = str(result.envelope.get("run_id", ""))
    zap = ZapView(cli.state_file()).proxied_messages(PILOT_HOST)
    return PilotRun(result, zap, pilot_state(), run_audit(cli, run_id))


def _start(root: Path, *flags: str, env: dict[str, str] | None = None) -> LabCli:
    cli = LabCli(root, {**throwaway_credentials(), **(env or {})})
    cli.install_product("clinica-piloto", PILOT_PROFILE)
    up = cli.run("stack", "up", "clinica-piloto", *flags, timeout=420)
    assert up.code == 0, up.stdout + up.stderr
    return cli


@dataclass(frozen=True)
class PilotSession:
    """Uma pilha do piloto já usada: preflight e duas execuções seguidas, sem reiniciar."""

    cli: LabCli
    preflight: CliResult
    first: PilotRun
    second: PilotRun
    secure: bool


@pytest.fixture(scope="module", params=["vulnerable", "secure"])
def pilot_session(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[PilotSession]:
    require_docker()
    secure = request.param == "secure"
    cli = _start(
        tmp_path_factory.mktemp(f"pilot-{request.param}"), *(["--secure"] if secure else [])
    )
    try:
        preflight = cli.run("preflight", "clinica-piloto")
        first = _probe(cli)
        second = _probe(cli)
        yield PilotSession(cli, preflight, first, second, secure)
    finally:
        cli.stack_down()


def test_preflight_is_ready_for_every_account(pilot_session: PilotSession) -> None:
    result = pilot_session.preflight

    assert result.code == 0, result.stdout
    ok = {c["id"] for c in result.data["checks"] if c["ok"]}
    assert ok >= {"zap", "target_health"}
    assert {f"login:{a}" for a in ("admin_a", "medico_a", "paciente_a", "paciente_b")} <= ok
    assert {f"csrf:{a}" for a in ("admin_a", "medico_a", "paciente_a", "paciente_b")} <= ok


@pytest.mark.parametrize("which", ["first", "second"])
def test_the_whole_chain_is_created_by_the_mapped_accounts(
    pilot_session: PilotSession, which: str
) -> None:
    run: PilotRun = getattr(pilot_session, which)

    assert run.result.code == 0, run.result.stdout
    assert run.result.data["status"] == "completed"
    for name in CHAIN:
        assert run.operations[name]["outcome"] == "success", (name, run.operations[name])
    assert run.operations["criarConvenio"]["account"] == "admin_a"
    assert run.operations["criarMedico"]["account"] == "admin_a"
    assert run.operations["criarPaciente"]["account"] == "medico_a"
    assert run.operations["criarConsulta"]["account"] == "medico_a"
    assert run.operations["criarReceita"]["account"] == "medico_a"
    assert run.operations["obterPerfil"]["account"] == "paciente_a"


def test_each_run_created_exactly_one_row_per_chain_table(pilot_session: PilotSession) -> None:
    first = pilot_session.first.target["rows_created_since_startup"]
    second = pilot_session.second.target["rows_created_since_startup"]

    assert {t: first[t] for t in CREATED_TABLES} == dict.fromkeys(CREATED_TABLES, 1)
    assert {t: second[t] for t in CREATED_TABLES} == dict.fromkeys(CREATED_TABLES, 2)


def test_unique_values_avoid_409_on_a_second_consecutive_run_without_reset(
    pilot_session: PilotSession,
) -> None:
    for run in (pilot_session.first, pilot_session.second):
        assert run.outcomes["conflict"] == 0
        assert run.outcomes["validation_error"] == 0
    assert pilot_session.second.outcomes["success"] == pilot_session.first.outcomes["success"]


def test_reachability_of_both_runs_is_the_same_and_only_the_login_probe_fails(
    pilot_session: PilotSession,
) -> None:
    for run in (pilot_session.first, pilot_session.second):
        summary = run.result.data["summary"]
        failing = {n for n, op in run.operations.items() if op["outcome"] == "auth_error"}
        # A operação `login` do OpenAPI vai com credenciais geradas, que o alvo recusa de propósito.
        assert failing == {"login"}, run.outcomes
        assert summary["operations_total"] == 29
        # Medido: 26 tentadas (29 menos a notificação negada e os dois DELETE fora do escopo).
        assert summary["operations_sent"] == 26
        assert summary["successes"] == 25
        assert summary["reachability"] == pytest.approx(
            summary["successes"] / summary["operations_sent"], abs=1e-4
        )


def test_the_forbidden_notification_endpoint_is_never_called(pilot_session: PilotSession) -> None:
    for run in (pilot_session.first, pilot_session.second):
        assert run.operations["enviarNotificacao"]["outcome"] == "skipped_denied"
        assert run.target["notifications_sent"] == 0
        assert not [r for r in run.audit if r["path"] == FORBIDDEN]
        assert not [m for m in run.zap_messages if FORBIDDEN in request_line(m)[1]]
    assert not [r for r in proxy_audit(pilot_session.cli) if r["path"] == FORBIDDEN]


def test_every_write_in_the_zap_history_carried_the_xsrf_pair(pilot_session: PilotSession) -> None:
    writes = [
        m
        for m in pilot_session.first.zap_messages
        if request_line(m)[0] in WRITE_METHODS and not request_line(m)[1].endswith(LOGIN_PATH)
    ]

    assert len(writes) >= 8
    for message in writes:
        header = str(message["requestHeader"])
        lines = {
            ln.split(":", 1)[0].lower(): ln.split(":", 1)[1].strip()
            for ln in header.split("\r\n")[1:]
            if ":" in ln
        }
        token = lines.get("x-xsrf-token")
        assert token, request_line(message)
        assert f"XSRF-TOKEN={token}" in lines.get("cookie", ""), request_line(message)
    assert pilot_session.first.outcomes["csrf_error"] == 0


def test_login_traffic_never_enters_the_zap_history(pilot_session: PilotSession) -> None:
    run = pilot_session.first
    account_logins = [
        r
        for r in run.audit
        if r["phase"] == "decision" and r["operation_id"] == "auth.login" and r["route"] == "auth"
    ]

    zap_logins = [m for m in run.zap_messages if request_line(m)[1].endswith(LOGIN_PATH)]

    assert {r["account"] for r in account_logins} == {"admin_a", "medico_a", "paciente_a"}
    assert len(zap_logins) == 1  # só a operação de login do OpenAPI, com dados de regra
    assert not any(
        "password" in str(m["requestBody"]) and "it_" in str(m["requestBody"]) for m in zap_logins
    )


def test_logins_in_one_command_never_exceed_the_declared_rate(pilot_session: PilotSession) -> None:
    run = pilot_session.first
    stamps = sorted(
        datetime.fromisoformat(r["timestamp"])
        for r in run.audit
        if r["phase"] == "decision" and r["path"] == LOGIN_PATH
    )

    for index, stamp in enumerate(stamps):
        window = [s for s in stamps[index:] if s - stamp < timedelta(seconds=60)]
        assert len(window) <= 5
    assert run.outcomes["rate_limited"] == 0


def test_cli_and_proxy_audits_agree_and_nothing_left_the_scope(pilot_session: PilotSession) -> None:
    run = pilot_session.second
    start = datetime.fromisoformat(run.result.data["started_at"])
    end = datetime.fromisoformat(run.result.data["finished_at"])
    cli_allowed = sorted(
        (r["method"], r["path"])
        for r in run.audit
        if r["phase"] == "decision" and r["decision"] == "allowed"
    )

    proxy = proxy_audit(pilot_session.cli)
    inside = [r for r in proxy if start <= datetime.fromisoformat(r["ts"]) <= end]

    assert (
        sorted((r["method"], r["path"]) for r in inside if r["decision"] == "allow") == cli_allowed
    )
    assert [r for r in proxy if r["decision"] == "deny"] == []
    assert {(r["host"], r["port"]) for r in proxy} == {("clinica-piloto", 8080)}


@pytest.fixture(scope="module")
def tuned_pilot(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LabCli]:
    """Piloto com token de 5 s e 60 logins por minuto, para provar o vencimento no meio."""
    require_docker()
    cli = _start(
        tmp_path_factory.mktemp("pilot-tuned"),
        "--token-ttl",
        "5",
        env={"PILOT_LOGIN_MAX_PER_MINUTE": "60"},
    )
    target = cli.products / "clinica-piloto" / "target.yml"
    text = target.read_text(encoding="utf-8")
    assert "max_per_minute: 5\n" in text
    target.write_text(text.replace("max_per_minute: 5\n", "max_per_minute: 60\n"), encoding="utf-8")
    try:
        yield cli
    finally:
        cli.stack_down()


def test_a_token_that_expires_mid_run_is_renewed_once_per_request(tuned_pilot: LabCli) -> None:
    cli = tuned_pilot
    assert cli.run("preflight", "clinica-piloto").code == 0

    run = _probe(cli)

    assert run.result.code == 0, run.result.stdout
    for name in CHAIN:
        assert run.operations[name]["outcome"] == "success", (name, run.operations[name])
    retried = [op for op in run.operations.values() if op["attempts"] == 2]
    logins = [r for r in run.audit if r["phase"] == "decision" and r["path"] == LOGIN_PATH]
    assert retried, "nenhum token venceu durante a execução; ajuste o tempo de vida do teste"
    assert all(op["attempts"] <= 2 for op in run.operations.values())
    assert len(logins) > 4  # três contas + a operação de login + ao menos uma renovação
    assert run.outcomes["auth_error"] == 1  # só a operação de login do OpenAPI


def _write_rules(cli: LabCli, extra: list[dict[str, Any]]) -> None:
    path = cli.products / "clinica-piloto" / "data-rules.yml"
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules["rules"] = [r for r in rules["rules"] if r["match"].get("field") not in {"cpf", "codigo"}]
    rules["rules"].extend(extra)
    path.write_text(yaml.safe_dump(rules, sort_keys=False), encoding="utf-8")


def test_deliberately_bad_data_rules_are_reported_with_the_per_field_detail(
    tuned_pilot: LabCli,
) -> None:
    cli = tuned_pilot
    # CPF de onze dígitos iguais passa no padrão do OpenAPI, mas o alvo recusa o dígito verificador;
    # o código de convênio constante colide na segunda execução.
    _write_rules(
        cli,
        [
            {"match": {"field": "cpf"}, "generator": "constant", "args": {"value": "11111111111"}},
            # Genérica: o PUT do convênio reenvia o mesmo código e não troca o que o POST criou.
            {"match": {"field": "codigo"}, "generator": "constant", "args": {"value": "12345678"}},
        ],
    )
    cli.run("preflight", "clinica-piloto")

    first = _probe(cli)
    second = _probe(cli)

    assert first.result.code == 0
    assert second.result.code == 0
    invalid = first.operations["criarPaciente"]
    assert invalid["outcome"] == "validation_error"
    excerpt = invalid["untrusted_target_data"]["excerpt"]
    assert '"field": "cpf"' in excerpt
    assert '"rule": "Cpf"' in excerpt
    assert first.operations["criarConsulta"]["outcome"] == "skipped_dependency"
    conflict = second.operations["criarConvenio"]
    assert conflict["outcome"] == "conflict"
    assert '"field": "codigo"' in conflict["untrusted_target_data"]["excerpt"]


def _closed_window_today() -> str:
    start = (datetime.now(UTC).hour + 3) % 24
    return f"seg-dom {start:02d}:00-{start + 1:02d}:00 UTC"


def test_a_closed_window_exits_3_and_nothing_is_sent(tmp_path: Path) -> None:
    require_docker()
    cli = _start(tmp_path)
    try:
        target = cli.products / "clinica-piloto" / "target.yml"
        text = target.read_text(encoding="utf-8")
        assert '"seg-dom 00:00-24:00 America/Sao_Paulo"' in text
        target.write_text(
            text.replace("seg-dom 00:00-24:00 America/Sao_Paulo", _closed_window_today()),
            encoding="utf-8",
        )

        probe = cli.run("probe", "clinica-piloto")
        preflight = cli.run("preflight", "clinica-piloto")

        assert probe.code == 3, probe.stdout
        assert probe.envelope["error"]["code"] == "SCOPE_VIOLATION"
        assert preflight.code == 3, preflight.stdout
        assert proxy_audit(cli) == []
        by_endpoint = pilot_state()["requests_by_endpoint"]
        assert not [name for name in by_endpoint if name.startswith(("POST", "PUT", "PATCH"))]
        assert "GET /api/csrf" not in by_endpoint
    finally:
        cli.stack_down()
