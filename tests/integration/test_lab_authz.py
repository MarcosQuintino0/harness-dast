"""Teste de autorização entre contas (V1.4) contra a Clínica Piloto, nos modos vulnerável e seguro.

Nível RÁPIDO: uma pilha por modo, um `probe` e um `authz` com todas as verificações. Prova o
CONTRATO do estágio, não o gabarito: as oito verificações aparecem com estado, nenhum `DELETE`
sai, todo pedido do `authz` passa pela cerca, nenhum segredo vai para os artefatos, os recursos
criados e a restauração ficam registrados e o `run` liga o estágio por padrão. As observações
das verificações são gravadas em `HDAST_IT_METRICS_DIR/lab-authz-<modo>-v3.json`. A prova da
V1.5.3 também verifica os papéis compartilhados e a detecção entre pacientes.

A cópia do perfil instalada na pasta descartável liga `authz.allow_writes`, o que no laboratório
faz o papel da carta de autorização e declara médicos compartilhados. O perfil versionado não é
alterado.
"""

import json
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from harness_dast.domain.authz_config import CHECK_ORDER
from tests.integration.lab_support import (
    PILOT_PROFILE,
    LabCli,
    proxy_audit,
    require_docker,
    run_audit,
)
from tests.integration.run_support import (
    ZapHistory,
    files_containing,
    record_metrics,
    secret_values,
    throwaway_pilot_env,
)

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

PILOT_BASE = "http://clinica-piloto:8080"
MODES = ("vulnerable", "secure")
ROLE_ORDER_LINE = "  role_order: [paciente, medico, admin]"
# Tabela tirada do `auth.account_map` do próprio perfil: o que ele atribui só a admin ou a médico
# não é do paciente. Declaração de laboratório; quem a faria num produto real é o dono.
MATRIX_YAML = """
  access_matrix:
    - { operation: criarConvenio, allow: [admin], deny: [paciente] }
    - { operation: atualizarConvenio, allow: [admin], deny: [paciente] }
    - { operation: criarMedico, allow: [admin], deny: [paciente] }
    - { operation: criarPaciente, allow: [medico], deny: [paciente] }
    - { operation: criarReceita, allow: [medico], deny: [paciente] }
"""
HIGH_TECHNIQUES = ("authz_horizontal", "authz_mass_assignment", "authz_excessive_data")
NEW_CHECKS = (
    "anonymous_access",
    "tampered_token",
    "access_matrix",
    "horizontal_write",
    "mass_assignment",
)


@dataclass
class AuthzLab:
    """O que foi medido em um modo, coletado enquanto a pilha dele estava no ar."""

    mode: str
    authz: dict[str, Any]
    cli_audit: list[dict[str, Any]]
    proxy_rows: list[dict[str, Any]]
    secret_hits: list[str]
    seconds: dict[str, float]
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    report_text: str = ""
    patient_list_has_items: bool = False

    def authz_rows(self, phase: str) -> list[dict[str, Any]]:
        """Linhas da trilha da CLI que pertencem ao `authz` (operation_id com prefixo `authz:`)."""
        return [
            row
            for row in self.cli_audit
            if row["phase"] == phase and str(row["operation_id"]).startswith("authz:")
        ]

    def proxy_in_authz_window(self) -> list[dict[str, Any]]:
        """Linhas do proxy entre o início e o fim do `authz` (inclui o login que ele fizer)."""
        start, end = self.authz["started_at"], self.authz["finished_at"]
        return [row for row in self.proxy_rows if start <= _iso(row["ts"]) <= end]


def _iso(value: str) -> str:
    """Normaliza o carimbo do proxy (`+00:00`) para comparar com o do `authz.json`."""
    return value.replace("Z", "+00:00")


def _install_with_writes(cli: LabCli) -> None:
    """Copia o perfil do piloto para a pasta descartável e liga `authz.allow_writes` só lá."""
    installed = cli.install_product("clinica-piloto", PILOT_PROFILE) / "target.yml"
    text = installed.read_text(encoding="utf-8")
    assert ROLE_ORDER_LINE in text, "o perfil do piloto deixou de declarar authz.role_order"
    installed.write_text(
        text.replace(
            ROLE_ORDER_LINE,
            ROLE_ORDER_LINE + "\n  allow_writes: true\n  shared_roles: [medico]" + MATRIX_YAML,
        ),
        encoding="utf-8",
    )


def _run_summary(cli: LabCli, *flags: str) -> dict[str, Any]:
    """Roda `hdast run` e devolve o código de saída e os estágios do `run.json`."""
    started = time.monotonic()
    done = cli.run("run", "clinica-piloto", *flags, timeout=3000)
    run_id = str(done.data.get("run_id") or done.envelope.get("run_id") or "")
    run_json = cli.runs / run_id / "run.json"
    loaded = json.loads(run_json.read_text(encoding="utf-8")) if run_json.is_file() else {}
    return {
        "flags": list(flags),
        "exit_code": done.code,
        "seconds": round(time.monotonic() - started, 1),
        "stages": {s["name"]: s for s in loaded.get("stages", [])},
    }


def _measure(cli: LabCli, mode: str) -> AuthzLab:
    seconds: dict[str, float] = {}

    def timed(name: str, started: float) -> None:
        seconds[name] = round(time.monotonic() - started, 1)

    started = time.monotonic()
    flags = ["--build", "--secure"] if mode == "secure" else ["--build"]
    assert cli.run("stack", "up", "clinica-piloto", *flags, timeout=600).code == 0
    timed("stack_up", started)
    assert cli.run("preflight", "clinica-piloto").code == 0
    started = time.monotonic()
    probe = cli.run("probe", "clinica-piloto", timeout=900)
    assert probe.code == 0, probe.stdout[-500:]
    timed("probe", started)
    run_id = str(probe.envelope["run_id"])
    started = time.monotonic()
    done = cli.run("authz", "clinica-piloto", "--run", run_id, timeout=1500)
    timed("authz", started)
    assert done.code == 0, done.stdout[-800:]
    authz = json.loads((cli.runs / run_id / "authz.json").read_text(encoding="utf-8"))
    history = ZapHistory(cli.state_file())
    patient_list_has_items = any(
        "GET http://clinica-piloto:8080/api/pacientes?" in str(m["requestHeader"])
        and bool(json.loads(str(m["responseBody"])).get("items"))
        for m in history.all_messages(PILOT_BASE)
        if "GET http://clinica-piloto:8080/api/pacientes?" in str(m["requestHeader"])
        and str(m["responseBody"]).lstrip().startswith("{")
    )
    needles = secret_values(cli, history, PILOT_BASE)
    hits = files_containing(cli.runs, needles, [done.stdout, done.stderr])
    proxy_rows = proxy_audit(cli)
    hits += [
        f"proxy:{p.name}"
        for p in (cli.state / "stacks").rglob("audit.jsonl")
        if any(n in p.read_text(encoding="utf-8", errors="replace") for n in needles)
    ]
    lab = AuthzLab(mode, authz, run_audit(cli, run_id), proxy_rows, hits, seconds)
    lab.patient_list_has_items = patient_list_has_items
    lab.report_text = _report_text(cli, run_id)
    started = time.monotonic()
    lab.runs["skip_scan"] = _run_summary(cli, "--skip-scan")
    lab.runs["skip_scan_no_authz"] = _run_summary(cli, "--skip-scan", "--no-authz")
    timed("run_skip_scan_pair", started)
    return lab


def _report_text(cli: LabCli, run_id: str) -> str:
    """Varre uma operação de leitura e gera o `report.md` da execução do `authz`."""
    scan = cli.run(
        "scan", "clinica-piloto", "--run", run_id, "--only", "buscarPacientesPorNome",
        "--max-minutes", "3", timeout=900,
    )  # fmt: skip
    assert scan.code in {0, 3}, scan.stdout[-500:]
    assert cli.run("report", "clinica-piloto", "--run", run_id).code in {0, 1}
    return (cli.runs / run_id / "report.md").read_text(encoding="utf-8")


def _observations(lab: AuthzLab) -> dict[str, Any]:
    authz = lab.authz
    reasons: dict[str, Counter[str]] = {check: Counter() for check in CHECK_ORDER}
    for item in authz["not_tested"]:
        reasons[item["check"]][item["reason"]] += 1
    by_technique = Counter(f["technique"] for f in authz["findings"])
    posts = [r for r in lab.authz_rows("result") if r["method"] == "POST"]
    return {
        "mode": lab.mode,
        "seconds": lab.seconds,
        "status": authz["status"],
        "requests_sent": authz["requests_sent"],
        "created_resources": authz["created_resources"],
        "accounts": authz["accounts"],
        "checks": {
            c["check"]: {k: c[k] for k in ("status", "candidates", "tested", "findings", "message")}
            for c in authz["checks"]
        },
        "findings_by_technique": dict(by_technique),
        "findings_by_severity": dict(Counter(f["proposed_severity"] for f in authz["findings"])),
        "findings": [
            {k: f[k] for k in ("technique", "proposed_severity", "method", "path_template")}
            | {k: f[k] for k in ("operation_id", "fields", "variants", "actor_role", "owner_role")}
            for f in authz["findings"]
        ],
        "not_tested_by_check": {c: dict(r) for c, r in reasons.items() if r},
        "shared_role_not_tested": [
            {k: item[k] for k in ("check", "operation_id", "method", "path")}
            for item in authz["not_tested"]
            if item["reason"] == "shared_role"
        ],
        "authz_requests_by_method": dict(Counter(r["method"] for r in lab.authz_rows("decision"))),
        "authz_post_results": dict(Counter(r["status"] for r in posts)),
        "authz_write_results": dict(
            Counter(
                f"{r['method']} {r['status']}"
                for r in lab.authz_rows("result")
                if r["method"] in {"PUT", "PATCH"}
            )
        ),
        "proxy_rows_in_window": len(lab.proxy_in_authz_window()),
        "authz_transport_errors": dict(
            Counter(
                f"{str(r['operation_id']).split(':')[1]}/{r['error']}"
                for r in lab.authz_rows("result")
                if r["error"]
            )
        ),
        "authz_result_statuses": dict(Counter(str(r["status"]) for r in lab.authz_rows("result"))),
        "runs": lab.runs,
        "access_matrix": authz["access_matrix"],
        "report_has_matrix_section": "Tabela quem pode o quê" in lab.report_text,
    }


@pytest.fixture(scope="module", params=MODES)
def lab(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[AuthzLab]:
    require_docker()
    mode = str(request.param)
    cli = LabCli(tmp_path_factory.mktemp(f"authz-{mode}"), throwaway_pilot_env())
    _install_with_writes(cli)
    try:
        measured = _measure(cli, mode)
        record_metrics(f"lab-authz-{mode}-v3", _observations(measured))
        yield measured
    finally:
        cli.stack_down()


def test_all_eight_checks_appear_in_authz_json_with_a_status(lab: AuthzLab) -> None:
    names = [item["check"] for item in lab.authz["checks"]]
    assert names == list(CHECK_ORDER)
    assert len(names) == 8
    assert {item["status"] for item in lab.authz["checks"]} <= {
        "completed",
        "partial",
        "skipped",
        "disabled",
    }
    assert lab.authz["status"] == "completed"
    assert set(NEW_CHECKS) <= set(names)


def test_no_delete_request_left_the_harness(lab: AuthzLab) -> None:
    sent = {row["method"] for row in lab.cli_audit} | {row["method"] for row in lab.proxy_rows}
    assert "DELETE" not in sent


def test_every_authz_request_went_through_the_fence_and_none_was_out_of_scope(
    lab: AuthzLab,
) -> None:
    allowed = [r for r in lab.authz_rows("decision") if r["decision"] == "allowed"]
    denied = [r for r in lab.authz_rows("decision") if r["decision"] == "denied"]
    assert denied == []
    assert len(allowed) == lab.authz["requests_sent"]
    assert len(allowed) > 0
    window = lab.proxy_in_authz_window()
    assert not [row for row in window if row["decision"] != "allow"]
    # Pedido que estourou o tempo no cliente pode não ter linha no proxy dentro da janela; todo
    # pedido que recebeu resposta tem de ter.
    answered = [r for r in lab.authz_rows("result") if r["status"] is not None]
    assert len(window) >= len(answered)


def test_no_token_or_secret_appears_in_the_artifacts_audits_or_cli_output(lab: AuthzLab) -> None:
    assert lab.secret_hits == []


def test_created_resources_match_the_posts_the_authz_sent_and_got_accepted(lab: AuthzLab) -> None:
    created = [
        row
        for row in lab.authz_rows("result")
        if row["method"] == "POST" and row["status"] is not None and 200 <= row["status"] < 300
    ]
    assert lab.authz["created_resources"] == len(created)


def test_writes_were_sent_only_because_the_copy_of_the_profile_allows_them(lab: AuthzLab) -> None:
    methods = Counter(r["method"] for r in lab.authz_rows("decision"))
    assert methods["PUT"] + methods["PATCH"] + methods["POST"] > 0
    mass = next(c for c in lab.authz["checks"] if c["check"] == "mass_assignment")
    assert "Não rodou: escrita não autorizada" not in str(mass["message"])


def test_in_secure_mode_no_authz_finding_is_high(lab: AuthzLab) -> None:
    if lab.mode != "secure":
        pytest.skip("só vale no modo seguro")
    assert not [f for f in lab.authz["findings"] if f["proposed_severity"] == "high"]


def test_in_vulnerable_mode_at_least_one_technique_proved_in_v1_1_reports_a_finding(
    lab: AuthzLab,
) -> None:
    if lab.mode != "vulnerable":
        pytest.skip("só vale no modo vulnerável")
    techniques = {f["technique"] for f in lab.authz["findings"]}
    assert techniques & set(HIGH_TECHNIQUES)


def test_run_skip_scan_records_the_authz_stage_as_skipped_with_the_right_reason(
    lab: AuthzLab,
) -> None:
    asked = lab.runs["skip_scan"]["stages"]["authz"]
    switched_off = lab.runs["skip_scan_no_authz"]["stages"]["authz"]
    assert asked["status"] == "skipped"
    assert "--skip-scan" in asked["message"]
    assert "--no-authz" not in asked["message"]
    assert switched_off["status"] == "skipped"
    assert "--no-authz" in switched_off["message"]
    assert asked["message"] != switched_off["message"]


def test_every_denied_cell_of_the_access_matrix_has_a_verdict_and_allowed_cells_are_not_tested(
    lab: AuthzLab,
) -> None:
    matrix = lab.authz["access_matrix"]
    assert matrix is not None
    assert len(matrix["rows"]) == 5
    cells = [cell for row in matrix["rows"] for cell in row["cells"]]
    denied = [c for c in cells if c["declared"] == "deny"]
    assert denied
    assert {c["result"] for c in denied} <= {"passed", "failed", "not_tested"}
    allowed = [c for c in cells if c["declared"] == "allow"]
    assert {c["result"] for c in allowed} <= {"declared_allowed", "proved_allowed"}
    summary = next(c for c in lab.authz["checks"] if c["check"] == "access_matrix")
    assert summary["status"] != "disabled"


def test_the_report_has_the_access_matrix_section(lab: AuthzLab) -> None:
    assert "Tabela quem pode o quê" in lab.report_text


def test_no_authz_request_timed_out_on_the_way_to_the_target(lab: AuthzLab) -> None:
    errors = [r["error"] for r in lab.authz_rows("result") if r["error"]]
    assert errors == []


@pytest.mark.parametrize(
    ("check", "operation"),
    [("horizontal", "buscarPaciente"), ("horizontal_write", "atualizarPaciente")],
)
def test_operacao_de_medico_registra_motivo_compartilhado(
    lab: AuthzLab, check: str, operation: str
) -> None:
    assert any(
        note["check"] == check
        and note["operation_id"] == operation
        and note["reason"] == "shared_role"
        for note in lab.authz["not_tested"]
    )


def test_medicos_compartilhados_nao_produzem_achados_horizontais(lab: AuthzLab) -> None:
    assert not [
        finding
        for finding in lab.authz["findings"]
        if finding["technique"] in {"authz_horizontal", "authz_horizontal_write"}
        and finding["actor_role"] == finding["owner_role"] == "medico"
    ]


def test_escrita_horizontal_em_paciente_por_medico_nao_e_enviada(lab: AuthzLab) -> None:
    assert not [
        row
        for row in lab.authz_rows("decision")
        if row["operation_id"] == "authz:write:atualizarPaciente"
    ]


def test_bola_entre_pacientes_permanece_detectavel_no_modo_vulneravel(lab: AuthzLab) -> None:
    if lab.mode != "vulnerable":
        pytest.skip("controle positivo exige modo vulneravel")
    assert any(
        finding["technique"] == "authz_horizontal"
        and finding["operation_id"] == "buscarConsulta"
        and finding["actor_role"] == finding["owner_role"] == "paciente"
        and finding["actor_account"] != finding["owner_account"]
        for finding in lab.authz["findings"]
    )


def test_paginacao_traz_itens_para_excessive_data(lab: AuthzLab) -> None:
    assert lab.patient_list_has_items
    assert not [
        n
        for n in lab.authz["not_tested"]
        if n["check"] == "excessive_data"
        and n["operation_id"] == "listarPacientes"
        and n["reason"] == "no_sample_data"
    ]
