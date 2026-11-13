"""`hdast run` seguido de `hdast cleanup` contra o Oracle Free do piloto, pela pilha gerenciada.

`hdast stack up clinica-piloto --oracle` sobe ZAP, proxy, piloto e Oracle; um humano (aqui, o
teste) cria o usuário de banco só da limpeza com `lab/pilot/cleanup/create-cleanup-user.sql`;
`hdast run` cria dados sintéticos (probe e varredura); `hdast cleanup --dry-run` mostra as
contagens (sem token: a CLI não emite nenhum), a CLI via subprocesso (sem terminal) recusa
apagar, e só uma pessoa digitando o nome do produto no terminal (aqui, um dublê do terminal no
caso de uso em processo) apaga. Critério: as contagens de linhas do
`/internal/eval/state` voltam EXATAMENTE à semente. O Oracle leva cerca de 80 s para subir e usa
cerca de 1,7 GiB; ZAP e Oracle juntos cabem no Docker Desktop de 6,7 GiB desta máquina de lab.
Nível rápido: `run --skip-scan` e uma varredura de duas escritas. Pulado sem Docker ou sem a
imagem do Oracle.
"""

import re
import secrets
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import oracledb
import pytest

from tests.integration.lab_support import (
    PILOT_MANAGEMENT,
    PILOT_PROFILE,
    LabCli,
    require_docker,
)
from tests.integration.run_support import MemorySampler, pilot_requests_by_endpoint, record_metrics

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

ORACLE_IMAGE = "gvenzl/oracle-free:23-slim-faststart"
PILOT_IMAGE = "hdast-clinica-piloto:1.0.0"
ORACLE_DSN = "127.0.0.1:21521/FREEPDB1"
USER_SQL = Path(__file__).parents[2] / "lab" / "pilot" / "cleanup" / "create-cleanup-user.sql"


def _has_image(name: str) -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        done = subprocess.run(  # noqa: S603 - comando fixo do teste
            [docker, "image", "inspect", name], capture_output=True, timeout=40, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return done.returncode == 0


def _rows() -> dict[str, int]:
    import httpx

    state = httpx.get(PILOT_MANAGEMENT + "/internal/eval/state", timeout=20, trust_env=False)
    return dict(state.json()["rows"])


def _create_cleanup_user(system_password: str, cleaner_password: str) -> None:
    """Executa o SQL versionado (`create-cleanup-user.sql`) como SYSTEM, trocando `&1`."""
    statements = [
        line.strip().rstrip(";").replace("&1", cleaner_password)
        for line in USER_SQL.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]
    connection = oracledb.connect(user="system", password=system_password, dsn=ORACLE_DSN)
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM dba_users WHERE username = 'HDAST_LIMPEZA'")
        if cursor.fetchone()[0]:
            cursor.execute("DROP USER HDAST_LIMPEZA CASCADE")
        for statement in statements:
            cursor.execute(statement)
    finally:
        connection.close()


@pytest.fixture(scope="module")
def oracle_cli(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LabCli]:
    require_docker()
    for image in (ORACLE_IMAGE, PILOT_IMAGE):
        if not _has_image(image):
            pytest.skip(f"a imagem {image} não existe localmente")
    env = {}
    for name in ("ADMIN", "MEDICO", "PACIENTE_A", "PACIENTE_B"):
        env[f"PILOT_{name}_USERNAME"] = f"it_{secrets.token_hex(4)}"
        env[f"PILOT_{name}_PASSWORD"] = secrets.token_urlsafe(18)
    cli = LabCli(tmp_path_factory.mktemp("oracle-run"), env)
    cli.install_product("clinica-piloto", PILOT_PROFILE, ())
    try:
        up = cli.run("stack", "up", "clinica-piloto", "--oracle", timeout=900)
        if up.code != 0:
            pytest.skip(f"a pilha com Oracle não subiu nesta máquina: {up.stdout[-300:]}")
        yield cli
    finally:
        cli.stack_down()


def test_run_then_cleanup_returns_the_row_counts_to_the_seed(oracle_cli: LabCli) -> None:
    target_env = oracle_cli.state_file()["target_env"]
    _create_cleanup_user(
        target_env["PILOT_ORACLE_PASSWORD"], target_env["PILOT_ORACLE_CLEANUP_PASSWORD"]
    )
    seed = _rows()
    # Nível rápido: o `run` faz preflight e probe (`--skip-scan`) e a varredura é só de duas
    # escritas, para provar que a limpeza também apaga o que o VARREDOR criou.
    flags = ["--skip-scan"]
    with MemorySampler() as sampler:
        result = oracle_cli.run("run", "clinica-piloto", *flags, timeout=2400)
        scan = oracle_cli.run(
            "scan",
            "clinica-piloto",
            "--run",
            str(result.data["run_id"]),
            "--only",
            "criarConvenio",
            "--only",
            "criarMedico",
            "--max-minutes",
            "6",
            timeout=900,
        )

    assert result.code == 0, result.stdout[-600:]
    assert scan.code in {0, 3}, scan.stdout[-600:]
    summary = result.data
    run_id = str(summary["run_id"])
    assert summary["cleanup_command"] == f"hdast cleanup clinica-piloto --run {run_id} --dry-run"
    assert "cleanup" not in " ".join(stage["name"] for stage in summary["stages"])
    created = _rows()
    assert created != seed, "o run não criou dados no piloto"
    assert not any("DELETE" in key for key in pilot_requests_by_endpoint(PILOT_MANAGEMENT))

    dry = oracle_cli.run("cleanup", "clinica-piloto", "--run", run_id, "--dry-run")
    assert dry.code == 0, dry.stdout[-600:]
    assert re.search(r"hdc-[\w-]+", dry.stderr + dry.stdout) is None  # sem token em lugar nenhum
    assert _rows() == created  # o --dry-run desfez tudo

    refused = oracle_cli.run("cleanup", "clinica-piloto", "--run", run_id)  # sem TTY
    assert refused.code == 2, refused.stdout[-600:]
    assert _rows() == created

    done = oracle_cli.confirm_cleanup_as_person("clinica-piloto", run_id, "clinica-piloto")
    assert (done.status, done.committed) == ("committed", True)
    assert _rows() == seed
    assert sampler.peaks
    record_metrics(
        "oracle-cleanup",
        {
            "run_exit_code": result.code,
            "flags": flags,
            "stages": [(x["name"], x["status"], x["duration_seconds"]) for x in summary["stages"]],
            "seed_rows": seed,
            "rows_after_run": created,
            "cleanup": {
                "status": done.status,
                "total_rows": done.total_rows,
                "committed": done.committed,
            },
            "peak_memory_mib": {k: round(v) for k, v in sampler.peaks.items()},
        },
    )
