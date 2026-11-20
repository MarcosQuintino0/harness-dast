"""`authz`: a tabela "quem pode o quê" (ADR 0041) testada contra a clínica falsa."""

from typing import Any

import pytest

from harness_dast.application.authz.service import Authz, AuthzRequest
from harness_dast.domain.authz.matrix import AuthzConfigError
from harness_dast.domain.authz.result import AuthzNotTested, AuthzResult
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.probe_exchange import ExchangeLog, ExchangeRecord
from tests.fakes.authz.rig import AuthzRig, Clinic

REPORTS: dict[str, Any] = {
    "operation": "listarRelatorios",
    "allow": ["admin"],
    "deny": ["paciente"],
}
CONVENIO: dict[str, Any] = {"operation": "criarConvenio", "allow": ["admin"], "deny": ["paciente"]}
MATRIX: dict[str, Any] = {"access_matrix": [REPORTS]}


def run_authz(rig: AuthzRig, **changes: Any) -> AuthzResult:
    probe = rig.run_probe()
    request = AuthzRequest(product="agenda", run_id=probe.run_id, **changes)
    return rig.authz().execute(request)


def matrix_requests(rig: AuthzRig) -> list[HttpRequest]:
    return [r for r in rig.target.requests if r.operation_id.startswith("authz:matrix:")]


def cell(result: AuthzResult, operation: str, role: str) -> Any:
    assert result.access_matrix is not None
    row = next(r for r in result.access_matrix.rows if r.operation_id == operation)
    return next(c for c in row.cells if c.role == role)


def notes(result: AuthzResult, reason: str) -> list[AuthzNotTested]:
    return [n for n in result.not_tested if n.check == "access_matrix" and n.reason == reason]


def summary(result: AuthzResult) -> Any:
    return next(c for c in result.checks if c.check == "access_matrix")


def test_a_server_that_denies_the_forbidden_role_passes_the_cell() -> None:
    rig = AuthzRig(Clinic(), authz=MATRIX)

    result = run_authz(rig, checks=("access_matrix",))

    assert result.findings == ()
    paciente = cell(result, "listarRelatorios", "paciente")
    assert (paciente.result, paciente.status, paciente.account) == ("passed", 403, "pac_a")
    assert cell(result, "listarRelatorios", "admin").result == "proved_allowed"
    assert (summary(result).candidates, summary(result).tested) == (1, 1)
    assert summary(result).status == "completed"


def test_a_server_that_accepts_the_forbidden_role_is_a_high_bfla_finding_per_role() -> None:
    rig = AuthzRig(Clinic(bfla=True), authz=MATRIX)

    result = run_authz(rig, checks=("access_matrix",))

    [finding] = result.findings
    assert finding.technique == "authz_access_matrix"
    assert (finding.proposed_severity, finding.cwe) == ("high", 285)
    assert finding.owasp_api_2023.startswith("API5:2023")
    assert (finding.actor_account, finding.actor_role, finding.owner_account) == (
        "pac_a",
        "paciente",
        "adm",
    )
    assert finding.fields == ("paciente",)
    assert (finding.baseline_status, finding.observed_status) == (200, 200)
    assert cell(result, "listarRelatorios", "paciente").result == "failed"
    assert summary(result).findings == 1


def test_exactly_one_request_per_denied_cell_goes_out_as_authz_matrix() -> None:
    rig = AuthzRig(Clinic(), authz=MATRIX)

    run_authz(rig, checks=("access_matrix",))

    assert [(r.method, r.operation_id, r.account) for r in matrix_requests(rig)] == [
        ("GET", "authz:matrix:listarRelatorios", "pac_a")
    ]


def test_get_runs_without_allow_writes_but_post_does_not() -> None:
    rig = AuthzRig(
        Clinic(bfla=True),
        authz={"allow_writes": False, "access_matrix": [REPORTS, CONVENIO]},
    )

    result = run_authz(rig, checks=("access_matrix",))

    assert cell(result, "listarRelatorios", "paciente").result == "failed"
    blocked = cell(result, "criarConvenio", "paciente")
    assert (blocked.result, blocked.reason) == ("not_tested", "writes_not_allowed")
    assert [r.method for r in matrix_requests(rig)] == ["GET"]
    assert notes(result, "writes_not_allowed")


def test_post_runs_with_allow_writes_and_a_created_resource_is_reported() -> None:
    rig = AuthzRig(Clinic(bfla=True), authz={"access_matrix": [CONVENIO]})

    result = run_authz(rig, checks=("access_matrix",))

    [finding] = result.findings
    assert finding.method == "POST"
    assert "permanece no alvo" in finding.evidence
    assert result.created_resources == 1
    assert [r.method for r in matrix_requests(rig)] == ["POST"]


def test_a_denying_server_passes_the_post_cell_too() -> None:
    rig = AuthzRig(Clinic(), authz={"access_matrix": [CONVENIO]})

    result = run_authz(rig, checks=("access_matrix",))

    assert cell(result, "criarConvenio", "paciente").result == "passed"
    assert result.created_resources == 0


def test_a_delete_is_never_sent_whatever_the_profile_says() -> None:
    rig = AuthzRig(Clinic(bfla=True), authz={"access_matrix": [REPORTS, CONVENIO]})

    run_authz(rig)

    assert all(r.method != "DELETE" for r in rig.target.requests)


def test_the_scope_guard_refuses_a_matrix_request_to_a_denied_path() -> None:
    rig = AuthzRig(Clinic(bfla=True), authz=MATRIX)
    probe = rig.run_probe()
    outside = ExchangeRecord(
        operation_id="listarRelatorios",
        method="GET",
        path="/api/relatorios",
        target="/api/admin/relatorios",
        account="adm",
        status=200,
    )
    rig.store.exchanges[probe.run_id] = ExchangeLog(
        run_id=probe.run_id, product="agenda", exchanges=(outside,)
    )

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("access_matrix",))
    )

    assert [r for r in rig.target.requests if "/api/admin/" in r.url] == []
    assert cell(result, "listarRelatorios", "paciente").reason == "scope_denied"
    assert notes(result, "scope_denied")
    assert result.findings == ()


def test_the_probe_already_proving_a_forbidden_role_is_a_finding_without_any_request() -> None:
    table = {"operation": "buscarConsulta", "allow": ["admin"], "deny": ["paciente"]}
    rig = AuthzRig(Clinic(), authz={"access_matrix": [table]})

    result = run_authz(rig, checks=("access_matrix",))

    forbidden = cell(result, "buscarConsulta", "paciente")
    assert (forbidden.result, forbidden.source) == ("failed", "probe")
    assert matrix_requests(rig) == []
    assert [f.technique for f in result.findings] == ["authz_access_matrix"]
    assert "probe já obteve" in result.findings[0].evidence


def test_a_role_that_is_not_in_the_rule_is_not_tested_and_not_called_forbidden() -> None:
    rig = AuthzRig(Clinic(bfla=True), authz={"access_matrix": [{"operation": "listarRelatorios"}]})

    result = run_authz(rig, checks=("access_matrix",))

    assert cell(result, "listarRelatorios", "paciente").result == "unspecified"
    assert matrix_requests(rig) == []
    assert result.findings == ()
    assert [n.reason for n in notes(result, "nothing_to_deny")] == ["nothing_to_deny"]


def test_vertical_skips_the_operation_the_table_covers_and_the_table_reports_it() -> None:
    rig = AuthzRig(Clinic(bfla=True), authz=MATRIX)

    result = run_authz(rig, checks=("vertical", "access_matrix"))

    assert {f.technique for f in result.findings} == {"authz_access_matrix"}
    skipped = [
        n
        for n in result.not_tested
        if n.check == "vertical" and n.operation_id == "listarRelatorios"
    ]
    assert [n.reason for n in skipped] == ["covered_by_access_matrix"]


def test_vertical_still_covers_the_operation_when_the_matrix_check_is_off() -> None:
    rig = AuthzRig(Clinic(bfla=True), authz={**MATRIX, "disabled_checks": ["access_matrix"]})

    result = run_authz(rig, checks=("vertical",))

    assert "authz_vertical" in {f.technique for f in result.findings}
    assert result.access_matrix is None


def test_without_a_table_the_check_says_so_and_there_is_no_matrix() -> None:
    rig = AuthzRig(Clinic())

    result = run_authz(rig, checks=("access_matrix",))

    assert result.access_matrix is None
    assert summary(result).status == "skipped"
    assert summary(result).candidates == 0
    assert "sem authz.access_matrix" in summary(result).message
    assert matrix_requests(rig) == []


def test_a_window_closed_stops_the_check_and_keeps_the_partial_table() -> None:
    class Engaged:
        def engaged(self) -> bool:
            return True

    rig = AuthzRig(Clinic(bfla=True), authz=MATRIX)
    probe = rig.run_probe()
    stage = Authz(
        profiles=rig.profiles,
        specs=rig._specs(),
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        store=rig.store,
        artifacts=rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
        kill_switch=Engaged(),
    )

    result = stage.execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("access_matrix",))
    )

    assert result.status == "stopped_window"
    waiting = cell(result, "listarRelatorios", "paciente")
    assert (waiting.result, waiting.reason) == ("not_tested", "not_run")
    assert result.findings == ()


def test_an_unknown_operation_in_the_table_is_refused_before_any_request() -> None:
    rig = AuthzRig(
        Clinic(), authz={"access_matrix": [{"operation": "naoExiste", "deny": ["admin"]}]}
    )
    probe = rig.run_probe()
    before = len(rig.target.requests)

    with pytest.raises(AuthzConfigError) as caught:
        rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id))

    assert caught.value.code == "AUTHZ_CONFIG_INVALID"
    assert len(rig.target.requests) == before


def test_a_role_without_an_account_in_the_table_is_refused() -> None:
    rig = AuthzRig(Clinic(), authz={"access_matrix": [{**REPORTS, "deny": ["recepcao"]}]})
    probe = rig.run_probe()

    with pytest.raises(AuthzConfigError):
        rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id))


def test_an_operation_both_public_and_in_the_table_is_refused() -> None:
    rig = AuthzRig(Clinic(), authz={**MATRIX, "public_operations": ["listarRelatorios"]})
    probe = rig.run_probe()

    with pytest.raises(AuthzConfigError):
        rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id, dry_run=True))


def test_dry_run_counts_the_denied_cells_and_sends_nothing() -> None:
    rig = AuthzRig(Clinic(bfla=True), authz={"access_matrix": [REPORTS, CONVENIO]})
    probe = rig.run_probe()
    before = len(rig.target.requests)

    result = rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id, dry_run=True))

    assert len(rig.target.requests) == before
    assert summary(result).candidates == 2
    assert result.access_matrix is None
    assert rig.artifacts.authz == {}


def test_the_matrix_is_written_to_authz_json_without_any_response_value() -> None:
    rig = AuthzRig(Clinic(bfla=True), authz=MATRIX)

    result = run_authz(rig, checks=("access_matrix",))

    assert rig.artifacts.authz[result.run_id].access_matrix == result.access_matrix
    dumped = result.model_dump_json()
    assert '"access_matrix"' in dumped
    assert "tok-" not in dumped
