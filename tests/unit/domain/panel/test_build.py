"""Montagem do `PanelView`: estados, nomes simples, falhas graves e dado ausente."""

from datetime import date

import pytest

from harness_dast.domain.authz.result import AuthzFinding, AuthzResult
from harness_dast.domain.panel.build import build_panel_view
from harness_dast.domain.panel.model import PanelCommand, PanelExplanation, PanelView
from harness_dast.domain.panel.sources import parse_moment
from harness_dast.domain.probe_result import ArtifactHashes, RunManifest
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.run import RunLimits
from harness_dast.domain.run_summary import StageRecord
from tests.fakes.zap_alerts import zap_alert
from tests.unit.domain.panel.helpers import (
    ZONE,
    bare,
    findings_report,
    run_summary,
    sources,
    spec_operations,
    view,
)
from tests.unit.domain.report.helpers import RUN_ID, entry, operation, probe_result, scan_result


def _states(panel_view: object) -> dict[str, str]:
    return {item.operation_id: item.state for item in panel_view.functions}  # type: ignore[attr-defined]


# ---------------------------------------------------------------- identificação


def test_identity_carries_product_run_time_mode_and_authorization() -> None:
    ident = view().identity

    assert ident.product == "vampi"
    assert ident.product_name == "Vampi"
    assert ident.run_id == RUN_ID
    assert ident.started_at is not None
    assert (ident.started_at.hour, ident.started_at.minute) == (20, 8)  # UTC-3
    assert ident.duration_seconds == 1680.0
    assert ident.fence_mode == "strict"
    assert ident.authorization_reference == "CHG-4821"
    assert ident.authorization_valid_until == date(2999, 12, 31)
    assert ident.harness_version is None


def test_identity_without_run_json_takes_the_time_from_the_files() -> None:
    ident = view(summary=None).identity

    assert ident.started_at is not None
    assert ident.finished_at is not None
    assert ident.duration_seconds is not None
    assert ident.duration_seconds > 0


def test_identity_falls_back_to_the_run_id_stamp_when_no_file_has_a_time() -> None:
    ident = build_panel_view(bare()).identity

    assert ident.started_at is not None
    assert ident.started_at.isoformat().startswith("2026-11-13T05:15:32")
    assert ident.duration_seconds is None
    assert ident.fence_mode is None
    assert ident.authorization_valid_until is None


@pytest.mark.parametrize("text", [None, "", "ontem", "2026-13-99T00:00:00"])
def test_parse_moment_returns_none_for_invalid_text(text: str | None) -> None:
    assert parse_moment(text, ZONE) is None


def test_parse_moment_treats_a_time_without_zone_as_utc() -> None:
    moment = parse_moment("2026-11-13T23:00:00", ZONE)

    assert moment is not None
    assert moment.hour == 20


# ---------------------------------------------------------------- funções


def test_function_names_use_the_openapi_summary_then_the_operation_id() -> None:
    names = {item.operation_id: item.name for item in view().functions}

    assert names["obter"] == "Ver usuário"
    assert names["listar"] == "listar"


def test_function_area_is_the_first_tag_or_outras() -> None:
    areas = {item.operation_id: item.area for item in view().functions}

    assert areas["obter"] == "Usuários"
    assert areas["criar"] == "Outras"


def test_function_states_cover_the_five_cases_with_a_reason_when_not_tested() -> None:
    by_id = {item.operation_id: item for item in view().functions}

    assert by_id["obter"].state == "severe"
    assert by_id["obter"].finding_ids
    assert by_id["apagar"].state == "forbidden"
    assert "DELETE" in (by_id["apagar"].reason or "")
    assert by_id["listar"].state == "failed"
    assert "400 ou 422" in (by_id["listar"].reason or "")
    assert by_id["criar"].state == "not_tried"
    assert by_id["nova"].state == "not_tried"
    assert by_id["nova"].reason == "O alcance não tentou esta função."


def test_a_function_without_a_severe_finding_is_just_attacked() -> None:
    clean = findings_report(alerts=[zap_alert("9", risk="Low")])

    assert _states(view(findings=clean))["obter"] == "tested"


def test_functions_keep_the_openapi_order_and_add_what_only_the_probe_knows() -> None:
    only_probe = view(operations=())

    assert [item.operation_id for item in only_probe.functions][:2] == ["obter", "criar"]
    assert {item.area for item in only_probe.functions} == {"Outras"}
    assert only_probe.functions[0].name == "obter"
    assert only_probe.functions[0].method == "GET"


def test_a_truncated_scan_is_attacked_with_a_reason() -> None:
    cut = scan_result([entry("obter", "GET", "/users/v1/{username}", 4, outcome="truncated")])

    by_id = {item.operation_id: item for item in view(scan=cut).functions}

    assert by_id["obter"].state == "severe"
    assert "cortada" in (by_id["obter"].reason or "")


# ---------------------------------------------------------------- falhas


def test_severe_findings_keep_the_proposed_severity_and_the_recorded_evidence() -> None:
    (finding,) = view().severe

    assert finding.severity == "high"
    assert finding.origin == "zap"
    assert finding.operation_id == "obter"
    assert finding.function_name == "Ver usuário"
    assert finding.evidence is not None
    assert finding.cwe == 89


def _with_evidence(**evidence: object) -> FindingsReport:
    base = findings_report()
    proof = base.findings[0].evidence.model_copy(update=evidence)
    changed = base.findings[0].model_copy(update={"evidence": proof})
    return base.model_copy(update={"findings": (changed,)})


def test_confidence_is_strong_when_the_recorded_response_shows_the_failure() -> None:
    shown = _with_evidence(available=True, zap_evidence="HTTP/1.1 500 Internal Server Error")

    assert view(findings=shown).severe[0].confidence == 2


@pytest.mark.parametrize(
    "evidence",
    [
        {"available": True, "zap_evidence": ""},
        {"available": True, "zap_evidence": "   "},
        {"available": False, "zap_evidence": "HTTP/1.1 500"},
    ],
)
def test_confidence_stays_to_confirm_without_a_recorded_proof(evidence: dict[str, object]) -> None:
    assert view(findings=_with_evidence(**evidence)).severe[0].confidence == 1


def test_the_zap_proposed_confidence_does_not_lower_a_proven_failure() -> None:
    base = _with_evidence(available=True, zap_evidence="HTTP/1.1 500")
    low = base.findings[0].model_copy(update={"proposed_confidence": "low"})

    assert view(findings=base.model_copy(update={"findings": (low,)})).severe[0].confidence == 2


def test_the_measured_example_has_two_strong_proofs_and_one_to_confirm() -> None:
    # Clínica Piloto (execução f087): dois erros 500 depois de uma aspa (o ZAP os propôs "low") e
    # uma falha por demora, sem trecho na resposta (o ZAP a propôs "medium").
    base = findings_report()
    proof = base.findings[0].evidence.model_copy(
        update={"available": True, "zap_evidence": "HTTP/1.1 500"}
    )
    strong = base.findings[0].model_copy(update={"evidence": proof, "proposed_confidence": "low"})
    delay = strong.model_copy(
        update={
            "finding_id": "F-00000002",
            "proposed_confidence": "medium",
            "evidence": proof.model_copy(update={"zap_evidence": ""}),
        }
    )
    twin = strong.model_copy(update={"finding_id": "F-00000003"})
    report = base.model_copy(update={"findings": (strong, delay, twin)})

    verdict = view(findings=report).verdict

    assert (verdict.severe_count, verdict.strong_count, verdict.to_confirm_count) == (3, 2, 1)


def test_the_agent_suspecting_a_false_positive_lowers_the_step_to_confirm() -> None:
    from harness_dast.domain.finding import TriageNote

    shown = _with_evidence(available=True, zap_evidence="HTTP/1.1 500")
    suspected = shown.findings[0].model_copy(
        update={"triage": TriageNote(suspected_false_positive=True, reason="parece esperado")}
    )

    report = shown.model_copy(update={"findings": (suspected,)})

    assert view(findings=report).severe[0].confidence == 1


def test_the_severe_finding_carries_the_repro_with_the_account_of_the_probe() -> None:
    shown = _with_evidence(
        available=True,
        zap_evidence="HTTP/1.1 500",
        request_header="GET http://alvo/users/v1/x HTTP/1.1\nHost: alvo",
    )
    base = sources()
    assert base.probe is not None
    ops = tuple(
        item.model_copy(update={"account": "user_a"}) if item.operation_id == "obter" else item
        for item in base.probe.operations
    )

    (finding,) = view(
        findings=shown, probe=base.probe.model_copy(update={"operations": ops})
    ).severe

    assert finding.repro is not None
    assert finding.repro.account == "user_a"
    assert finding.repro.target == "/users/v1/x"
    assert finding.proposed_confidence is not None


def test_a_finding_without_recorded_evidence_has_no_repro() -> None:
    assert view().severe[0].repro is None


def test_command_times_are_shown_in_the_zone_of_the_panel() -> None:
    from datetime import UTC, datetime

    command = PanelCommand(
        command="hdast doctor vampi", at=datetime(2026, 11, 13, 23, 8, tzinfo=UTC)
    )

    (shown,) = view(commands=(command,)).commands or ()

    assert shown.at is not None
    assert shown.at.hour == 20  # fuso -03:00 do cenário
    assert shown.at == command.at


def test_confidence_never_reaches_the_third_step_without_a_person() -> None:
    assert all(item.confidence < 3 for item in view().severe)


def test_counts_and_groups_come_from_the_findings_report() -> None:
    counts = view().counts

    assert counts is not None
    assert counts.high == 1
    assert counts.total == 1
    assert counts.groups == 1
    assert len(view().groups) == 1


def test_authz_findings_count_as_severe_and_are_marked_as_their_own_origin() -> None:
    finding = AuthzFinding(
        finding_id="A-12345678",
        fingerprint="a" * 64,
        technique="authz_horizontal",
        title="Acesso a dado de outra conta",
        proposed_severity="high",
        cwe=639,
        owasp_api_2023="API1:2023",
        operation_id="obter",
        method="GET",
        path_template="/users/v1/{username}",
        actor_account="user_a",
        evidence="user_a leu o recurso de user_b",
        description="d",
        solution="s",
    )
    authz = AuthzResult(
        run_id=RUN_ID,
        product="vampi",
        status="completed",
        started_at="2026-11-13T05:20:00+00:00",
        finished_at="2026-11-13T05:21:00+00:00",
        findings=(finding,),
    )

    panel_view = view(authz=authz)

    assert panel_view.counts is not None
    assert panel_view.counts.high == 2
    origins = {item.origin for item in panel_view.severe}
    assert origins == {"zap", "authz"}
    assert panel_view.verdict.severe_count == 2
    assert not any(
        "decidir se autoriza o teste entre contas" in item.text.lower()
        for item in panel_view.next_steps
    )


# ---------------------------------------------------------------- veredito e etapas


def test_a_finished_run_has_four_done_stages_and_the_authz_and_negative_skipped() -> None:
    panel_view = view()

    assert panel_view.verdict.kind == "finished"
    assert [item.key for item in panel_view.stages] == [
        "preflight",
        "probe",
        "scan",
        "authz",
        "negative",
        "report",
    ]
    assert [item.state for item in panel_view.stages] == [
        "done",
        "done",
        "done",
        "skipped",
        "skipped",
        "done",
    ]
    assert panel_view.stages[2].seconds == 1140.0


def test_verdict_counts_attacked_attempted_and_strong_findings() -> None:
    verdict = view().verdict

    assert verdict.functions_total == 5
    assert verdict.functions_attempted == 3
    assert verdict.functions_attacked == 1
    assert verdict.severe_count == 1


def test_a_run_stopped_in_the_scan_is_partial_with_the_stage_and_the_reason() -> None:
    summary = run_summary(
        status="interrupted",
        stages=(
            StageRecord(name="preflight", status="ok"),
            StageRecord(name="probe", status="ok"),
            StageRecord(name="scan", status="interrupted", message="Uma pessoa mandou parar."),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="not_run"),
        ),
        stop_requested=True,
    )

    verdict = view(summary=summary).verdict

    assert verdict.kind == "partial"
    assert verdict.stopped_stage == "scan"
    assert verdict.reason == "Uma pessoa mandou parar."
    assert verdict.stop_requested is True


def test_stages_after_the_cut_are_pending_and_have_no_time() -> None:
    summary = run_summary(
        status="failed",
        stages=(
            StageRecord(name="preflight", status="ok", duration_seconds=3),
            StageRecord(name="probe", status="ok", duration_seconds=4),
            StageRecord(name="scan", status="failed", duration_seconds=9, message="ZAP fora."),
            StageRecord(name="authz", status="not_run", duration_seconds=0),
            StageRecord(name="report", status="not_run", duration_seconds=0),
        ),
    )

    stages = {item.key: item for item in view(summary=summary).stages}

    assert stages["scan"].state == "cut"
    assert stages["scan"].message == "ZAP fora."
    assert stages["authz"].state == "pending"
    assert stages["report"].state == "pending"
    assert stages["report"].seconds is None


def test_a_failure_before_any_attack_is_an_error() -> None:
    summary = run_summary(
        status="failed",
        stages=(
            StageRecord(name="preflight", status="failed", message="login recusado"),
            StageRecord(name="probe", status="not_run"),
            StageRecord(name="scan", status="not_run"),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="not_run"),
        ),
    )

    verdict = view(summary=summary, probe=None, scan=None, findings=None).verdict

    assert verdict.kind == "error"
    assert verdict.stopped_stage == "preflight"
    assert verdict.reason == "login recusado"
    assert verdict.severe_count is None


def test_without_run_json_a_probe_only_run_is_partial_at_the_scan() -> None:
    verdict = view(summary=None, scan=None, findings=None).verdict

    assert verdict.kind == "partial"
    assert verdict.stopped_stage == "scan"
    assert verdict.functions_attacked is None


def test_a_scan_that_stopped_early_makes_a_file_only_run_partial() -> None:
    stopped = scan_result(
        [entry("obter", "GET", "/users/v1/{username}", 4)], status="stopped_deadline"
    )

    verdict = view(summary=None, scan=stopped).verdict

    assert verdict.kind == "partial"
    assert verdict.stopped_stage == "scan"


def test_without_any_file_the_view_is_an_error_with_nothing_invented() -> None:
    panel_view = build_panel_view(bare())

    assert panel_view.verdict.kind == "error"
    assert panel_view.functions == ()
    assert panel_view.traffic is None
    assert panel_view.counts is None
    assert panel_view.severe == ()
    assert panel_view.measurements.metrics_available is False
    assert panel_view.measurements.tokens_total is None
    assert panel_view.commands is None
    assert all(item.seconds is None for item in panel_view.stages)


# ---------------------------------------------------------------- tráfego e passos


def test_traffic_is_the_one_of_the_scan_and_marked_unmeasured_without_the_proxy_audit() -> None:
    panel_view = view()

    assert panel_view.traffic is not None
    assert panel_view.traffic_measured is False


def test_left_out_lists_functions_scan_cuts_authz_and_the_blind_spots() -> None:
    kinds = [item.kind for item in view().left_out]

    assert kinds.count("functions") == 3
    assert "authz" in kinds
    assert kinds.count("blind") == 2


def test_next_steps_have_owners_and_never_widen_scope_or_promise_safety() -> None:
    steps = view().next_steps
    text = " ".join(item.text for item in steps).lower()

    assert {item.owner for item in steps} == {"qa", "owner"}
    assert "seguro" not in text
    assert "aprovad" not in text
    assert "amplie" not in text
    assert any("chamado" in item.text or "à mão" in item.text for item in steps)
    assert any("entre contas" in item.text for item in steps if item.owner == "owner")


def test_a_partial_run_asks_to_understand_the_stop_and_keeps_scope_and_limits() -> None:
    summary = run_summary(
        status="failed",
        stages=(
            StageRecord(name="preflight", status="ok"),
            StageRecord(name="probe", status="ok"),
            StageRecord(name="scan", status="failed", message="m"),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="not_run"),
        ),
    )

    texts = [item.text for item in view(summary=summary).next_steps]

    assert any("parou" in text and "limites" in text for text in texts)


# ---------------------------------------------------------------- medições e ganchos


def test_hooks_enter_as_ready_values_and_may_be_empty() -> None:
    command = PanelCommand(command="hdast probe vampi", translation="Tentou as funções.")
    explanation = PanelExplanation(title="Comando no banco", what_to_do="Corrigir.")
    finding_id = view().severe[0].finding_id

    hooked = view(commands=(command,), explanations={finding_id: explanation})
    empty = view(commands=(), explanations={})

    assert hooked.commands == (command,)
    assert hooked.severe[0].explanation == explanation
    assert empty.commands == ()
    assert empty.severe[0].explanation is None
    assert view().commands is None


def test_authorization_validity_is_none_without_a_profile() -> None:
    ident = view(
        authorization_reference=None, authorization_valid_until=None, fence_mode=None
    ).identity

    assert ident.authorization_reference is None
    assert ident.authorization_valid_until is None
    assert ident.fence_mode is None


def test_operations_without_summary_or_tags_fall_back() -> None:
    plain = spec_operations(summary=None, tag=None)

    by_id = {item.operation_id: item for item in view(operations=plain).functions}

    assert by_id["obter"].name == "obter"
    assert by_id["obter"].area == "Outras"


def test_a_probe_with_no_operations_does_not_break_the_view() -> None:
    empty_probe = probe_result([])
    empty_scan = scan_result([])

    panel_view = view(probe=empty_probe, scan=empty_scan, findings=None, operations=())

    assert panel_view.functions == ()
    assert panel_view.verdict.functions_attacked == 0
    assert operation("x", "GET", "/x").operation_id == "x"


# ---------------------------------------------------------------- endereço com nome de parâmetro


def with_empty_placeholder() -> PanelView:
    """O relatório guarda o endereço como `/users/v1/{}`; o Swagger sabe que é `{username}`."""
    base = sources()
    assert base.findings is not None
    items = tuple(
        item.model_copy(update={"path_template": "/users/v1/{}"}) for item in base.findings.findings
    )
    groups = tuple(
        group.model_copy(
            update={
                "locations": tuple(
                    loc.model_copy(update={"path_template": "/users/v1/{}"})
                    for loc in group.locations
                )
            }
        )
        for group in base.findings.groups
    )
    report = base.findings.model_copy(update={"findings": items, "groups": groups})
    return build_panel_view(sources(findings=report))


def test_an_address_with_empty_braces_gets_the_parameter_name_back_from_the_swagger() -> None:
    panel_view = with_empty_placeholder()

    assert panel_view.severe[0].path_template == "/users/v1/{username}"
    assert all(
        path == "/users/v1/{username}"
        for group in panel_view.groups
        for _, path, _ in group.locations
        if path.startswith("/users/v1/")
    )


def test_an_address_that_does_not_match_the_swagger_keeps_what_was_recorded() -> None:
    base = sources()
    assert base.findings is not None
    items = tuple(
        item.model_copy(update={"path_template": "/outra/{}"}) for item in base.findings.findings
    )
    panel_view = build_panel_view(
        sources(findings=base.findings.model_copy(update={"findings": items}))
    )

    assert panel_view.severe[0].path_template == "/outra/{}"


def test_the_start_without_run_json_is_the_run_id_stamp_never_a_stage_file_time() -> None:
    """Uma só hora de início: a do `run.json`; sem ele, a do carimbo do id (tela e índice)."""
    manifest = RunManifest(
        run_id=RUN_ID,
        command="preflight",
        product="vampi",
        harness_version="1",
        hashes=ArtifactHashes(),
        limits=RunLimits(requests_per_second=1, max_duration_minutes=1, zap_threads_per_host=1),
        seed=0,
        started_at="2026-11-13T05:16:40+00:00",
    )

    ident = view(summary=None, manifest=manifest).identity

    assert ident.started_at is not None
    assert ident.started_at.isoformat().startswith("2026-11-13T02:15:32")  # carimbo 05:15:32Z, -3 h


def test_functions_that_share_a_swagger_summary_are_listed_with_distinct_names() -> None:
    from harness_dast.domain.api_model import Operation

    operations = tuple(
        Operation(
            operation_id=f"dup_{method}",
            method=method,
            path="/api/duplicada/**",
            summary="Duplicada",
        )
        for method in ("get", "post", "put")
    )

    panel_view = build_panel_view(sources(operations=operations))

    names = [item.name for item in panel_view.functions if item.operation_id.startswith("dup_")]
    assert len(set(names)) == 3
    assert "Duplicada (POST /api/duplicada/**)" in names
