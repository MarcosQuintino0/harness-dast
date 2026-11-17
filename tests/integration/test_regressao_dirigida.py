"""Regressão dirigida e rápida (V1.12, L5): nada deixou de ser achado no laboratório.

Roteiro NÃO cego, uma asserção por falha, sem a varredura completa:

- Clínica Piloto vulnerável: H1 a H10 do gabarito (`evals/cases/clinica-piloto/case.yml`), com a H5
  pela leitura de dono (consultas mapeadas ao médico compartilhado, como no caso cego).
- Clínica Piloto segura: nenhum achado de autorização.
- VAmPI vulnerável: V1 (injeção de SQL) e V3 (autorização entre contas).

Só roda o que cada falha exige: `probe`, `authz` (em qualquer modo) e um `scan --only` nas
operações em que o ZAP detecta a falha. Os critérios vêm do mesmo gabarito da régua da avaliação
(`flaw_status`), então a regressão e a avaliação cega concordam sobre o que é "achada". H11
(injeção em cabeçalho, ADR 0092) fica fora: `detectable: false` até a trilha F.

Uso: `uv run pytest -m regressao_dirigida` (exige Docker e a trava do laboratório). O tempo de cada
cenário é gravado em `HDAST_IT_METRICS_DIR` (`regressao-dirigida-<cenário>`).
"""

import json
import secrets
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
import yaml

from evals.runner.cases import load_case
from evals.runner.checks_findings import ACHADA, flaw_status, read_findings
from evals.runner.models import Flaw
from tests.integration.lab_support import (
    PILOT_PROFILE,
    LabCli,
    proxy_audit,
    require_docker,
)
from tests.integration.run_support import record_metrics, throwaway_pilot_env
from tests.integration.test_lab_v155 import _install
from tests.integration.test_lab_vampi import SEEDED
from tests.integration.v112_resource_support import ResourceGuard, docker_runner, inventory
from tests.integration.v112_watch_diagnostic_support import collect_watch, docker_logs

pytestmark = [pytest.mark.integration, pytest.mark.regressao_dirigida]

# Operações em que o ZAP detecta H1 a H4 e H8 a H10 (H3 também vem do `authz`, CORS).
PILOT_SCAN_OPERATIONS = (
    "buscarPacientesPorNome",
    "buscarMedicoPorCrm",
    "baixarDocumento",
    "buscarConvenioPorCodigo",
    "baixarArquivo",
)
VAMPI_SCAN_OPERATION = "api_views.users.get_by_username"
VAMPI_CREATE_OPERATION = "api_views.books.add_new_book"
SCAN_MINUTES = "12"
MINUTES_GOAL = 20.0


def _flaws(name: str) -> dict[str, Flaw]:
    return {flaw.id: flaw for flaw in load_case(name).flaws if flaw.detectable}


PILOT_FLAWS = _flaws("clinica-piloto")
VAMPI_FLAWS = {key: value for key, value in _flaws("vampi").items() if key in {"V1", "V3"}}
FOUND_CASES = [("pilot-vulnerable", key) for key in PILOT_FLAWS] + [
    ("vampi-vulnerable", key) for key in VAMPI_FLAWS
]


@dataclass
class Lab:
    """O que um cenário produziu: achados, estágios com tempo e a trilha do proxy."""

    name: str
    findings: list[dict[str, Any]]
    authz_findings: list[dict[str, Any]]
    seconds: dict[str, float]
    proxy_rows: list[dict[str, Any]]
    exit_codes: dict[str, int] = field(default_factory=dict)


def _blind_profile(cli: LabCli) -> None:
    """Perfil do piloto como no caso cego: leitura de dono (H5), escrita entre contas e H9 amplo."""
    target = cli.install_product("clinica-piloto", PILOT_PROFILE) / "target.yml"
    profile = yaml.safe_load(target.read_text(encoding="utf-8"))
    profile.pop("cleanup", None)
    profile["scope"]["path_mode"] = "wide"
    profile["authz"].update({"allow_writes": True, "shared_roles": ["medico"]})
    profile["authz"].pop("role_order", None)
    operations = {"listarConsultas", "buscarConsulta", "criarConsulta", "atualizarStatusConsulta"}
    for rule in profile["auth"]["account_map"]:
        rule["operations"] = [op for op in rule["operations"] if op not in operations]
    profile["auth"]["account_map"].append({"account": "medico_a", "operations": sorted(operations)})
    target.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")


def _step(
    cli: LabCli, lab: dict[str, Any], name: str, *args: str, ok: set[int] | None = None
) -> Any:
    started = time.monotonic()
    done = cli.run(*args, timeout=1500)
    lab["seconds"][name] = round(time.monotonic() - started, 1)
    lab["exit_codes"][name] = done.code
    assert done.code in (ok or {0}), f"{name}: {done.stdout[-600:]}"
    return done


def _scan_flags(*operations: str) -> list[str]:
    flags = ["--max-minutes", SCAN_MINUTES]
    for operation in operations:
        flags += ["--only", operation]
    return flags


def _run_pilot(cli: LabCli, mode: str, lab: dict[str, Any]) -> list[str]:
    _blind_profile(cli)
    up = ["stack", "up", "clinica-piloto", "--build"] + (["--secure"] if mode == "secure" else [])
    _step(cli, lab, "stack_up", *up)
    _step(cli, lab, "preflight", "preflight", "clinica-piloto")
    probe = _step(cli, lab, "probe", "probe", "clinica-piloto")
    run_id = str(probe.envelope["run_id"])
    _step(cli, lab, "authz", "authz", "clinica-piloto", "--run", run_id)
    if mode == "vulnerable":
        _step(
            cli, lab, "scan", "scan", "clinica-piloto", "--run", run_id,
            *_scan_flags(*PILOT_SCAN_OPERATIONS), ok={0, 3},
        )  # fmt: skip
        _step(cli, lab, "report", "report", "clinica-piloto", "--run", run_id, ok={0, 1})
    return [run_id]


def _run_vampi(cli: LabCli, lab: dict[str, Any]) -> list[str]:
    _install(cli, "vampi")
    _step(cli, lab, "stack_up", "stack", "up", "vampi", "--build")
    _step(cli, lab, "preflight", "preflight", "vampi")
    # V3: a criação não devolve o título; só a leitura de dono fecha o par (ver test_v193).
    first = _step(cli, lab, "probe_authz", "probe", "vampi", "--only", VAMPI_CREATE_OPERATION)
    authz_run = str(first.envelope["run_id"])
    _step(cli, lab, "authz", "authz", "vampi", "--run", authz_run, "--check", "horizontal")
    # V1: injeção de SQL achada pelo ZAP numa operação só.
    second = _step(cli, lab, "probe_scan", "probe", "vampi")
    scan_run = str(second.envelope["run_id"])
    _step(
        cli, lab, "scan", "scan", "vampi", "--run", scan_run,
        *_scan_flags(VAMPI_SCAN_OPERATION), ok={0, 3},
    )  # fmt: skip
    # O `report` exige scan.json: só a execução do scan o tem; o authz vem do authz.json.
    _step(cli, lab, "report", "report", "vampi", "--run", scan_run, ok={0, 1})
    return [authz_run, scan_run]


SCENARIOS = ["pilot-vulnerable", "pilot-secure", "vampi-vulnerable"]


@pytest.fixture(scope="module", params=SCENARIOS)
def lab(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Lab]:
    """Um cenário por vez: a pilha do cenário anterior é derrubada antes da seguinte."""
    require_docker()
    name = str(request.param)
    product = "vampi" if name.startswith("vampi") else "clinica-piloto"
    env = (
        {**SEEDED, "HDAST_ZAP_API_KEY": secrets.token_hex(32)}
        if product == "vampi"
        else throwaway_pilot_env()
    )
    cli = LabCli(tmp_path_factory.mktemp(f"regressao-{name}"), env)
    state: dict[str, Any] = {"seconds": {}, "exit_codes": {}}
    guard = None
    if cli.env.get("HDAST_STACK_PROJECT_SUFFIX") == "-codex":
        guard = ResourceGuard(lambda: inventory(docker_runner(cli.env)))
    started = time.monotonic()
    completed = False
    stack_attempted = False
    try:
        if guard is not None:
            guard.before_up()
        stack_attempted = True
        run_ids = (
            _run_vampi(cli, state)
            if product == "vampi"
            else _run_pilot(cli, name.removeprefix("pilot-"), state)
        )
        total = round(time.monotonic() - started, 1)
        authz_files = [cli.runs / run_id / "authz.json" for run_id in run_ids]
        authz = [
            item
            for file in authz_files
            if file.is_file()
            for item in json.loads(file.read_text(encoding="utf-8"))["findings"]
        ]
        result = Lab(
            name,
            [*read_findings(cli.root), *authz],
            authz,
            {**state["seconds"], "total": total},
            proxy_audit(cli),
            state["exit_codes"],
        )
        # Nada saiu do escopo da carta: nenhum DELETE passou pelo proxy em cenário algum.
        assert not [r for r in result.proxy_rows if str(r.get("method", "")).upper() == "DELETE"]
        record_metrics(
            f"regressao-dirigida-{name}",
            {
                "seconds": result.seconds,
                "minutes": round(total / 60, 1),
                "within_goal": total / 60 < MINUTES_GOAL,
                "exit_codes": result.exit_codes,
                "findings": len(result.findings),
                "authz_findings": len(authz),
            },
        )
        completed = True
        yield result
    finally:
        watch: dict[str, Any] = {"status": "not_started", "categories": []}
        if stack_attempted:
            watch = (
                collect_watch(
                    guard, docker_runner(cli.env), docker_logs(cli.env), capture_created=True
                )
                if guard is not None
                else {"status": "unsupported_project", "categories": []}
            )
        try:
            if stack_attempted:
                cli.stack_down()
        finally:
            try:
                record_metrics(
                    f"regressao-dirigida-{name}-watch",
                    {
                        "status": "completed" if completed else "failed",
                        "seconds": round(time.monotonic() - started, 1),
                        "exit_codes": state["exit_codes"],
                        "watch": watch,
                    },
                )
            except OSError:
                sys.stderr.write("Não foi possível gravar o diagnóstico da vigia.\n")


# O fixture percorre os três cenários em ordem, uma pilha por vez; cada teste só vale no seu.
@pytest.mark.parametrize("flaw_id", [key for _, key in FOUND_CASES])
def test_falha_plantada_continua_achada(lab: Lab, flaw_id: str) -> None:
    flaws = PILOT_FLAWS if lab.name == "pilot-vulnerable" else VAMPI_FLAWS
    if flaw_id not in flaws or lab.name == "pilot-secure":
        pytest.skip(f"{flaw_id} não vale no cenário {lab.name}")
    assert flaw_status(flaws[flaw_id], lab.findings) == ACHADA, flaw_id


def test_modo_seguro_da_clinica_nao_tem_achado_de_autorizacao(lab: Lab) -> None:
    if lab.name != "pilot-secure":
        pytest.skip("só vale no cenário pilot-secure")
    assert lab.authz_findings == []
    assert lab.exit_codes["authz"] == 0


def test_roteiro_tem_o_gabarito_esperado() -> None:
    """A regressão cobre H1 a H10 e V1 e V3; H11 (cabeçalho) segue fora da nota."""
    assert sorted(PILOT_FLAWS, key=lambda key: int(key[1:])) == [f"H{n}" for n in range(1, 11)]
    assert sorted(VAMPI_FLAWS) == ["V1", "V3"]
    assert "H11" not in PILOT_FLAWS
