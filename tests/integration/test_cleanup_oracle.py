# ruff: noqa: S608
"""`hdast cleanup` contra um Oracle Free de verdade, com a Clínica Piloto criando o lixo.

Sobe o piloto com o perfil `oracle` de `lab/pilot/compose.yaml` sob um nome de projeto próprio,
com portas livres em 127.0.0.1 (nada colide com o lab principal) e um `.env` descartável com
senhas sorteadas, fora do repositório. Cria dados pela API como conta de teste (login + XSRF),
roda o `hdast cleanup` dentro do processo (executor Oracle real, modo thin) e confere as linhas
pelo endpoint de estado do piloto.

Pula limpo quando não há Docker, quando a imagem do Oracle ou do piloto não foi baixada/construída
ou quando o Oracle não fica saudável. O Oracle leva cerca de 80 s para ficar saudável.

Convenção para desenvolver: `HDAST_IT_STACK_DIR=<pasta com .env>` reaproveita uma pilha já em pé
(com os mesmos nomes de variável do `.env.example` do piloto mais `HDAST_IT_ORACLE_PORT`) e não
a derruba no fim.
"""

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import oracledb
import pytest
import yaml

from harness_dast.application.cleanup import CleanupReport, CleanupRequest
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.composition import build_cleanup
from harness_dast.domain.cleanup_plan import CleanupPlan
from harness_dast.domain.errors import ExitCode
from harness_dast.observability.logging import SecretRegistry
from tests.fakes.approvals import approve_product_on_disk
from tests.fakes.cleanup_ports import finished_manifest

pytestmark = pytest.mark.integration

REPO = Path(__file__).parents[2]
PILOT = REPO / "lab" / "pilot"
PROJECT = "hdastcleanit"
ORACLE_IMAGE = "gvenzl/oracle-free:23-slim-faststart"
PILOT_IMAGE = "hdast-clinica-piloto:1.0.0"
TABLES = ("CONVENIO", "MEDICO", "PACIENTE", "CONSULTA", "RECEITA")
UP_TIMEOUT_SECONDS = 600
CLEANER_USER = "HDAST_LIMPEZA"


@dataclass(frozen=True)
class Stack:
    """Endereços e credenciais descartáveis da pilha de teste."""

    env: dict[str, str]
    api: str
    mgmt: str
    oracle_port: int

    @property
    def oracle_dsn(self) -> str:
        return f"127.0.0.1:{self.oracle_port}/FREEPDB1"


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - comando fixo do teste, sem entrada externa
        args, capture_output=True, text=True, timeout=timeout, check=False, encoding="utf-8"
    )


def _skip_reason() -> str | None:
    if shutil.which("docker") is None:
        return "docker não está instalado"
    try:
        if _run(["docker", "info", "--format", "{{.ServerVersion}}"], 40).returncode != 0:
            return "o motor do Docker não responde"
        for image in (ORACLE_IMAGE, PILOT_IMAGE):
            if _run(["docker", "image", "inspect", image], 40).returncode != 0:
                return f"a imagem {image} não existe localmente (baixe ou construa em lab/pilot)"
    except subprocess.TimeoutExpired:
        return "o Docker não respondeu a tempo"
    return None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _generated_env() -> dict[str, str]:
    def password() -> str:
        return "Aa1_" + secrets.token_hex(8)

    oracle_password = password()
    return {
        "PILOT_ADMIN_USERNAME": "it_admin",
        "PILOT_ADMIN_PASSWORD": password(),
        "PILOT_MEDICO_USERNAME": "it_medico",
        "PILOT_MEDICO_PASSWORD": password(),
        "PILOT_MEDICO_B_USERNAME": "it_medico_b",
        "PILOT_MEDICO_B_PASSWORD": password(),
        "PILOT_PACIENTE_A_USERNAME": "it_paciente_a",
        "PILOT_PACIENTE_A_PASSWORD": password(),
        "PILOT_PACIENTE_B_USERNAME": "it_paciente_b",
        "PILOT_PACIENTE_B_PASSWORD": password(),
        "PILOT_VULNERABLE": "1",
        "PILOT_JWT_TTL_SECONDS": "300",
        "PILOT_LOGIN_MAX_PER_MINUTE": "100",
        "PILOT_XSRF_ENFORCED": "1",
        "PILOT_HOST_PORT": str(_free_port()),
        "PILOT_MGMT_HOST_PORT": str(_free_port()),
        "PILOT_ORACLE_PASSWORD": oracle_password,
        "PILOT_DB_URL": "jdbc:oracle:thin:@//oracle:1521/FREEPDB1",
        "PILOT_DB_USER": "clinica",
        "PILOT_DB_PASSWORD": oracle_password,
        "HDAST_IT_ORACLE_PORT": str(_free_port()),
    }


def _read_env(path: Path) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in path.read_text("utf-8").splitlines() if "=" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def _compose(directory: Path, *args: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "docker",
            "compose",
            "-p",
            PROJECT,
            "-f",
            str(PILOT / "compose.yaml"),
            "-f",
            str(directory / "override.yaml"),
            "--env-file",
            str(directory / ".env"),
            "--profile",
            "oracle",
            *args,
        ],
        timeout,
    )


def _bring_up(directory: Path) -> Stack:
    env = _generated_env()
    (directory / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()), "utf-8")
    # O compose do piloto não publica a porta do Oracle; o override a publica só em 127.0.0.1.
    (directory / "override.yaml").write_text(
        'services:\n  oracle:\n    ports:\n      - "127.0.0.1:${HDAST_IT_ORACLE_PORT}:1521"\n',
        "utf-8",
    )
    try:
        result = _compose(directory, "up", "-d", "--wait", "--no-build", timeout=UP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _compose(directory, "down", "-v", "--timeout", "20", timeout=120)
        pytest.skip("o Oracle não ficou saudável a tempo nesta máquina")
    if result.returncode != 0:
        logs = _compose(directory, "logs", "--tail", "30", timeout=60).stdout
        _compose(directory, "down", "-v", "--timeout", "20", timeout=120)
        pytest.fail(f"docker compose up falhou:\n{result.stderr[-1500:]}\n{logs[-1500:]}")
    return _stack_from(env)


def _stack_from(env: dict[str, str]) -> Stack:
    return Stack(
        env=env,
        api=f"http://127.0.0.1:{env['PILOT_HOST_PORT']}",
        mgmt=f"http://127.0.0.1:{env['PILOT_MGMT_HOST_PORT']}",
        oracle_port=int(env["HDAST_IT_ORACLE_PORT"]),
    )


def _create_cleanup_user(stack: Stack) -> None:
    """Cria o usuário de banco só da limpeza: SELECT e DELETE nas tabelas de teste, nada mais."""
    system_password = stack.env["PILOT_ORACLE_PASSWORD"]
    connection = oracledb.connect(user="system", password=system_password, dsn=stack.oracle_dsn)
    try:
        cursor = connection.cursor()
        cursor.execute(f"DROP USER {CLEANER_USER} CASCADE") if _user_exists(cursor) else None
        cursor.execute(
            f'CREATE USER {CLEANER_USER} IDENTIFIED BY "{stack.env["PILOT_ORACLE_PASSWORD"]}"'
        )
        cursor.execute(f"GRANT CREATE SESSION TO {CLEANER_USER}")
        for table in TABLES:
            cursor.execute(f"GRANT SELECT, DELETE ON CLINICA.{table} TO {CLEANER_USER}")
    finally:
        connection.close()


def _user_exists(cursor: Any) -> bool:
    cursor.execute("SELECT COUNT(*) FROM dba_users WHERE username = :n", n=CLEANER_USER)
    return bool(cursor.fetchone()[0])


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)
    existing = os.environ.get("HDAST_IT_STACK_DIR")
    if existing:
        current = _stack_from(_read_env(Path(existing) / ".env"))
        _create_cleanup_user(current)
        yield current
        return
    directory = tmp_path_factory.mktemp("pilot-oracle")
    started = _bring_up(directory)
    try:
        _create_cleanup_user(started)
        yield started
    finally:
        _compose(directory, "down", "-v", "--timeout", "20", timeout=180)


# ---------------------------------------------------------------- o piloto


def eval_state(stack: Stack) -> dict[str, int]:
    return dict(httpx.get(f"{stack.mgmt}/internal/eval/state", timeout=20).json()["rows"])


def reset_pilot(stack: Stack) -> dict[str, int]:
    assert httpx.post(f"{stack.mgmt}/internal/eval/reset", timeout=60).status_code < 300
    return eval_state(stack)


def _cpf(base: str) -> str:
    digits = [int(c) for c in base]
    for size in (9, 10):
        total = sum(d * w for d, w in zip(digits[:size], range(size + 1, 1, -1), strict=True))
        digits.append((total * 10 % 11) % 10)
    return "".join(str(d) for d in digits)


class Admin:
    """Cliente HTTP do piloto como a conta de teste de admin (login + XSRF)."""

    def __init__(self, stack: Stack) -> None:
        self._client = httpx.Client(base_url=stack.api, timeout=30)
        login = self._client.post(
            "/api/auth/login",
            json={
                "username": stack.env["PILOT_ADMIN_USERNAME"],
                "password": stack.env["PILOT_ADMIN_PASSWORD"],
            },
        )
        login.raise_for_status()
        self._bearer = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def create(self, path: str, body: dict[str, Any]) -> int:
        # Um token XSRF novo por escrita: o piloto pode girar o cookie depois de aceitar uma.
        csrf = self._client.get("/api/csrf").json()
        headers = {**self._bearer, csrf["headerName"]: csrf["token"]}
        response = self._client.post(path, json=body, headers=headers)
        assert response.status_code == 201, f"{path}: {response.status_code} {response.text}"
        return int(response.json()["id"])

    def close(self) -> None:
        self._client.close()


def create_junk(stack: Stack) -> None:
    """Cria um convênio, um médico, um paciente, uma consulta e uma receita como admin."""
    unique = secrets.token_hex(4)
    admin = Admin(stack)
    try:
        convenio = admin.create(
            "/api/convenios",
            {
                "codigo": str(int(unique, 16) % 10**8).zfill(8),
                "nome": "Plano IT",
                "tipo": "INDIVIDUAL",
                "coparticipacaoPercentual": 10,
            },
        )
        medico = admin.create(
            "/api/medicos",
            {
                "crm": f"{int(unique, 16) % 10**6:06d}-SP",
                "nome": "Dra. IT",
                "especialidade": "CLINICA_GERAL",
            },
        )
        paciente = admin.create(
            "/api/pacientes",
            {
                "convenioId": convenio,
                "cpf": _cpf(f"{int(unique, 16) % 10**9:09d}"),
                "dataNascimento": "1990-05-17",
                "email": f"it-{unique}@exemplo.test",
                "nome": "Paciente IT",
                "sexo": "OUTRO",
            },
        )
        consulta = admin.create(
            "/api/consultas",
            {
                "dataHora": (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "medicoId": medico,
                "motivo": "Rotina",
                "pacienteId": paciente,
                "valor": 120.5,
            },
        )
        admin.create(
            "/api/receitas",
            {
                "consultaId": consulta,
                "duracaoDias": 7,
                "medicamento": "Dipirona",
                "posologia": "1x ao dia",
            },
        )
    finally:
        admin.close()


# ------------------------------------------------------------- o produto


@dataclass(frozen=True)
class Workspace:
    products: Path
    runs: Path
    run_id: str
    started_at: datetime


def make_workspace(
    tmp_path: Path, stack: Stack, monkeypatch: pytest.MonkeyPatch, script: str | None = None
) -> Workspace:
    """Produto com o perfil do piloto + usuário de limpeza, e a execução que criou o lixo."""
    started_at = datetime.now(UTC) - timedelta(minutes=2)  # folga contra o relógio da VM do Docker
    run_id = f"{started_at:%Y-%m-%dT%H-%M-%SZ}-clinica-piloto-7f3a"
    pilot_profile = yaml.safe_load(
        (PILOT / "product-profile" / "target.yml").read_text(encoding="utf-8")
    )
    pilot_profile["environment"]["base_url"] = stack.api
    pilot_profile["scope"]["allow"][0].update({"host": "127.0.0.1", "port": int(stack.api[-5:])})
    pilot_profile["cleanup"].update(
        {
            "connection": {"secret_ref": "env:IT_ORACLE_DSN"},
            "user": {"secret_ref": "env:IT_ORACLE_USER"},
            "password": {"secret_ref": "env:IT_ORACLE_PASSWORD"},
            "allowed_tables": ["RECEITA", "CONSULTA", "PACIENTE", "MEDICO", "CONVENIO"],
            "max_rows": 50,
            "db_schema": "CLINICA",
        }
    )
    folder = tmp_path / "produtos" / "clinica-piloto"
    (folder / "cleanup").mkdir(parents=True)
    (folder / "target.yml").write_text(yaml.safe_dump(pilot_profile, sort_keys=False), "utf-8")
    (folder / "openapi.json").write_text("{}", "utf-8")
    sql = script if script is not None else (PILOT / "cleanup" / "cleanup.sql").read_text("utf-8")
    (folder / "cleanup" / "cleanup.sql").write_text(sql, "utf-8")
    approve_product_on_disk(tmp_path / "produtos", "clinica-piloto")  # a pessoa, no terminal
    runs = tmp_path / "runs"
    (runs / run_id).mkdir(parents=True)
    manifest = finished_manifest(
        run_id, "clinica-piloto", started_at, finished_at=datetime.now(UTC)
    )
    (runs / run_id / "manifest.json").write_text(manifest.model_dump_json(), "utf-8")
    for name, value in stack.env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("IT_ORACLE_DSN", stack.oracle_dsn)
    monkeypatch.setenv("IT_ORACLE_USER", CLEANER_USER)
    monkeypatch.setenv("IT_ORACLE_PASSWORD", stack.env["PILOT_ORACLE_PASSWORD"])
    monkeypatch.setenv("HDAST_RUNS_DIR", str(runs))
    return Workspace(tmp_path / "produtos", runs, run_id, started_at)


def hdast(
    capsys: pytest.CaptureFixture[str], workspace: Workspace, *extra: str
) -> tuple[int, dict[str, Any], str]:
    args = [
        "--json",
        "cleanup",
        "clinica-piloto",
        "--run",
        workspace.run_id,
        "--products-dir",
        str(workspace.products),
        *extra,
    ]
    code = run_app(build_app(), args)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


class TypedName:
    """Dublê do terminal: a pessoa digita `typed` no prompt (só o nome do produto confirma)."""

    def __init__(self, typed: str) -> None:
        self.typed = typed

    def confirm(self, plan: CleanupPlan) -> bool:
        return self.typed.strip() == plan.product


def confirm_as_person(workspace: Workspace, typed: str) -> CleanupReport:
    """Roda o caso de uso em processo, com a pessoa (dublê) num terminal interativo.

    A confirmação real exige terminal; o subprocesso do teste não tem, então este caminho exercita
    o caso de uso diretamente, com o mesmo executor Oracle da CLI.
    """
    use_case = build_cleanup(workspace.products, SecretRegistry(), TypedName(typed))
    return use_case.execute(
        CleanupRequest(
            product="clinica-piloto",
            run_id=workspace.run_id,
            dry_run=False,
            confirm_token=None,
            interactive=True,
        )
    )


def cli_without_terminal(workspace: Workspace) -> subprocess.CompletedProcess[str]:
    """`hdast cleanup` de verdade por subprocesso: sem TTY em stdin, a CLI tem de recusar."""
    return subprocess.run(  # noqa: S603 - interpretador atual e módulo do próprio projeto
        [
            sys.executable,
            "-m",
            "harness_dast",
            "--json",
            "cleanup",
            "clinica-piloto",
            "--run",
            workspace.run_id,
            "--products-dir",
            str(workspace.products),
        ],
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


def junk_rows(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {
        table: after[table] - before[table] for table in before if after[table] != before[table]
    }


# ------------------------------------------------------------------ os testes


def test_dry_run_then_a_person_typing_the_product_removes_only_the_junk_and_keeps_the_seed(
    stack: Stack,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed = reset_pilot(stack)
    workspace = make_workspace(tmp_path, stack, monkeypatch)
    create_junk(stack)
    with_junk = eval_state(stack)
    expected = {"convenio": 1, "medico": 1, "paciente": 1, "consulta": 1, "receita": 1}
    assert junk_rows(seed, with_junk) == expected

    code, dry, err = hdast(capsys, workspace, "--dry-run")

    assert code == ExitCode.OK, dry
    assert dry["data"]["status"] == "dry_run"
    assert {s["table"]: s["rows"] for s in dry["data"]["statements"]} == {
        "RECEITA": 1,
        "CONSULTA": 1,
        "PACIENTE": 1,
        "MEDICO": 1,
        "CONVENIO": 1,
    }
    assert eval_state(stack) == with_junk  # o --dry-run desfez tudo
    assert "hdc-" not in err + json.dumps(dry)  # a CLI não emite token nenhum

    refused = cli_without_terminal(workspace)  # a CLI de verdade, sem TTY, nunca apaga
    assert refused.returncode == ExitCode.USAGE, refused.stdout
    assert "terminal interativo" in json.loads(refused.stdout)["error"]["message"]
    assert eval_state(stack) == with_junk

    declined = confirm_as_person(workspace, "outro-nome")
    assert (declined.status, declined.committed) == ("declined", False)
    assert eval_state(stack) == with_junk

    done = confirm_as_person(workspace, "clinica-piloto")

    assert (done.status, done.committed) == ("committed", True)
    assert eval_state(stack) == seed  # volta exatamente ao estado de semente
    with_record = json.loads(
        (workspace.runs / workspace.run_id / "cleanup.json").read_text("utf-8")
    )
    assert with_record["total_rows"] == 5


def test_a_failing_statement_in_the_middle_leaves_the_database_unchanged(
    stack: Stack,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed = reset_pilot(stack)
    anchor = "CREATED_AT >= :run_start AND CREATED_BY IN (:account_1, :account_2)"
    # O comando 2 apaga o paciente antes da consulta: o Oracle recusa (ORA-02292).
    script = (
        f"DELETE FROM RECEITA WHERE {anchor};\n"
        f"DELETE FROM PACIENTE WHERE {anchor};\n"
        f"DELETE FROM CONSULTA WHERE {anchor};\n"
    )
    workspace = make_workspace(tmp_path, stack, monkeypatch, script)
    create_junk(stack)
    with_junk = eval_state(stack)

    code, envelope, _ = hdast(capsys, workspace, "--dry-run")

    assert code == ExitCode.CLEANUP
    assert envelope["error"]["code"] == "CLEANUP_FAILED"
    assert "comando 2" in envelope["error"]["message"]
    assert "PACIENTE" in envelope["error"]["message"]
    assert "ORA-02292" in envelope["error"]["message"]
    assert eval_state(stack) == with_junk  # a receita apagada pelo comando 1 voltou
    assert (
        json.loads((workspace.runs / workspace.run_id / "cleanup.json").read_text("utf-8"))[
            "failed_statement"
        ]
        == 2
    )
    reset_pilot(stack)
    assert eval_state(stack) == seed


def test_row_ceiling_exceeded_rolls_back_the_real_transaction(
    stack: Stack,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reset_pilot(stack)
    workspace = make_workspace(tmp_path, stack, monkeypatch)
    profile_path = workspace.products / "clinica-piloto" / "target.yml"
    profile = yaml.safe_load(profile_path.read_text("utf-8"))
    profile["cleanup"]["max_rows"] = 4
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), "utf-8")
    approve_product_on_disk(workspace.products, "clinica-piloto")  # `cleanup` não está na proteção
    create_junk(stack)
    with_junk = eval_state(stack)

    code, envelope, _ = hdast(capsys, workspace, "--dry-run")

    assert code == ExitCode.CLEANUP
    assert "acima do teto de 4" in envelope["error"]["message"]
    assert eval_state(stack) == with_junk


def test_forbidden_statement_is_refused_before_any_connection_is_opened(
    stack: Stack,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reset_pilot(stack)
    workspace = make_workspace(
        tmp_path, stack, monkeypatch, "DELETE FROM RECEITA WHERE ID > 0;\nDROP TABLE RECEITA;\n"
    )
    connections: list[object] = []
    real_connect = oracledb.connect

    def counting(*args: Any, **kwargs: Any) -> Any:
        connections.append(kwargs)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(oracledb, "connect", counting)
    before = eval_state(stack)

    code, envelope, _ = hdast(capsys, workspace, "--dry-run")

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert connections == []
    assert eval_state(stack) == before


def test_wrong_database_password_is_a_cleanup_error_without_leaking_it(
    stack: Stack,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reset_pilot(stack)
    workspace = make_workspace(tmp_path, stack, monkeypatch)
    monkeypatch.setenv("IT_ORACLE_PASSWORD", "senha-errada-SEGREDO-123")

    code, envelope, err = hdast(capsys, workspace, "--dry-run")

    assert code == ExitCode.CLEANUP
    assert "ORA-01017" in envelope["error"]["message"]
    assert "senha-errada-SEGREDO-123" not in json.dumps(envelope) + err
