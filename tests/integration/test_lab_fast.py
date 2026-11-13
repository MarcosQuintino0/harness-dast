"""Nível RÁPIDO da integração: poucos endpoints, uma pilha por grupo, sem nota contra o gabarito.

Serve ao ciclo conserta-e-roda: `uv run pytest -m lab_fast` (exige Docker). Os endpoints foram
escolhidos por cobrirem o mecanismo testado (uma escrita com XSRF, uma leitura com parâmetro), não
por terem falha plantada. O que o nível rápido NÃO valida: cobertura de todas as operações, a
política padrão de regras sobre o alvo inteiro, a comparação com o gabarito e o comportamento da
varredura por mais de alguns minutos (renovação de token em varredura longa, prazo, saúde do alvo
sob carga). Isso é do nível COMPLETO (`-m lab_full`).

Um teste curto prova que o limitador de taxa segura em valor baixo (5 req/s medidos na auditoria
do proxy), para que um perfil de laboratório rápido nunca deixe o freio sem prova.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.integration.lab_support import (
    PILOT_PROFILE,
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    LabCli,
    proxy_audit,
    require_docker,
)
from tests.integration.run_support import (
    Facts,
    Scenario,
    collect_facts,
    throwaway_pilot_env,
)

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

PILOT_BASE = "http://clinica-piloto:8080"
VAMPI_ENV = {
    "VAMPI_USER_A_USERNAME": "name1",
    "VAMPI_USER_A_PASSWORD": "pass1",
    "VAMPI_USER_B_USERNAME": "name2",
    "VAMPI_USER_B_PASSWORD": "pass2",
    "VAMPI_ADMIN_USERNAME": "admin",
    "VAMPI_ADMIN_PASSWORD": "pass1",
}
# Uma escrita com o par XSRF e uma leitura com parâmetro.
PILOT_OPERATIONS = ("criarConvenio", "buscarPacientesPorNome")
VAMPI_OPERATION = "api_views.users.get_by_username"


def _probe_and_scan(cli: LabCli, product: str, *operations: str) -> tuple[str, int]:
    # O preflight chama o health_path (no VAmPI, /createdb) e deixa o banco como a semente.
    assert cli.run("preflight", product).code == 0
    probe = cli.run("probe", product)
    assert probe.code == 0, probe.stdout[-500:]
    run_id = str(probe.envelope["run_id"])
    flags = [item for op in operations for item in ("--only", op)]
    scan = cli.run("scan", product, "--run", run_id, "--max-minutes", "6", *flags, timeout=900)
    assert scan.code in {0, 3}, scan.stdout[-500:]
    return run_id, scan.code


@pytest.fixture(scope="module")
def pilot_facts(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Facts]:
    require_docker()
    cli = LabCli(tmp_path_factory.mktemp("fast-pilot"), throwaway_pilot_env())
    cli.install_product("clinica-piloto", PILOT_PROFILE)
    try:
        assert cli.run("stack", "up", "clinica-piloto", timeout=600).code == 0
        run_id, _ = _probe_and_scan(cli, "clinica-piloto", *PILOT_OPERATIONS)
        result = cli.run("report", "clinica-piloto", "--run", run_id)
        scenario = Scenario("fast-pilot", cli, result, cli.runs / run_id, proxy_audit(cli), {}, 0.0)
        yield collect_facts(scenario, PILOT_BASE, pilot=True)
    finally:
        cli.stack_down()


def test_scanner_writes_carry_the_xsrf_pair_and_none_is_rejected_for_csrf(
    pilot_facts: Facts,
) -> None:
    csrf = pilot_facts.csrf
    assert csrf["writes_reached_target"] > 0
    assert csrf["writes_with_header"] == csrf["writes_reached_target"]
    assert csrf["writes_with_cookie"] == csrf["writes_reached_target"]
    assert csrf["csrf_rejected"] == 0


def test_every_scanner_request_carries_the_auth_token(pilot_facts: Facts) -> None:
    with_auth, total = pilot_facts.auth_on_scanner
    assert total > 0
    assert with_auth == total


def test_no_secret_reaches_any_artifact_the_proxy_audit_or_the_cli_output(
    pilot_facts: Facts,
) -> None:
    assert pilot_facts.secret_hits == []


def test_replacer_rules_are_all_removed_after_the_scan(pilot_facts: Facts) -> None:
    assert pilot_facts.rules_left == []


def test_scope_denials_counted_in_scan_json_match_the_proxy_audit(pilot_facts: Facts) -> None:
    scenario = pilot_facts.scenario
    scan = scenario.load("scan.json")
    traffic = scan["traffic"]
    assert traffic["enabled"] is True
    assert traffic["denied"] > 0
    report = (scenario.run_dir / "report.md").read_text(encoding="utf-8")
    assert f"{traffic['denied']} requisição(ões) que o varredor tentou" in report


@pytest.fixture(scope="module")
def slow_vampi(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, float]]:
    """Varre uma operação do VAmPI com o limite baixo (5 req/s) e devolve a taxa medida.

    O perfil do laboratório roda no teto (50 req/s) para os testes serem rápidos; aqui a cópia
    instalada é reduzida para o valor conservador do modelo, para o freio continuar com prova.
    """
    require_docker()
    cli = LabCli(tmp_path_factory.mktemp("fast-rate"), VAMPI_ENV)
    installed = cli.install_product("vampi", VAMPI_PROFILE, (VAMPI_OPENAPI,)) / "target.yml"
    fast = installed.read_text(encoding="utf-8")
    slow = fast.replace("requests_per_second: 50", "requests_per_second: 5").replace(
        "zap_threads_per_host: 8", "zap_threads_per_host: 2"
    )
    assert slow != fast, "o perfil do laboratório deixou de declarar 50 req/s e 8 threads"
    installed.write_text(slow, encoding="utf-8")
    try:
        assert cli.run("stack", "up", "vampi", timeout=600).code == 0
        run_id, _ = _probe_and_scan(cli, "vampi", VAMPI_OPERATION)
        traffic = _traffic(cli.runs / run_id)
        yield traffic
    finally:
        cli.stack_down()


def _traffic(run_dir: Path) -> dict[str, float]:
    import json

    scan = json.loads((run_dir / "scan.json").read_text(encoding="utf-8"))
    return dict(scan["traffic"])


def test_rate_limiter_holds_the_low_profile_rate_in_the_proxy_audit(
    slow_vampi: dict[str, float],
) -> None:
    assert slow_vampi["limit_rps"] == 5.0
    assert slow_vampi["allowed"] > 100
    assert slow_vampi["average_rps"] <= 5.25
    assert slow_vampi["peak_rps"] <= 6
