"""`report.html` com o estágio de autorização e com a cerca do ADR 0026: costuras da V1.1."""

import pytest

from harness_dast.domain.authz_findings import TECHNIQUE_LABEL
from harness_dast.domain.report_actions import next_steps
from harness_dast.domain.report_build import assemble_report
from harness_dast.domain.report_html import render_html
from harness_dast.domain.report_markdown import render_markdown
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.report_traffic import denied_rows, path_shape_warning
from harness_dast.domain.scope_labels import SCOPE_CODE_LABELS, label_for
from harness_dast.domain.scope_reason import ScopeReason
from harness_dast.domain.traffic import TrafficSummary
from tests.fakes.zap_alerts import zap_alert
from tests.unit.application.test_report_authz import authz_result
from tests.unit.domain.report_helpers import entry, operation, probe_result, scan_result
from tests.unit.domain.test_report_html import JWT, XSS, parse, report


def with_authz(*, findings: bool = True, **changes: object) -> FindingsReport:
    base = report([zap_alert("9")])
    result = authz_result(findings=findings).model_copy(update=changes)
    counts = {name: 0 for name in ("high", "medium", "low", "informational", "unknown")}
    for item in result.findings:
        counts[item.proposed_severity] += 1
    summary = base.summary.model_copy(update={"authz_by_severity": counts})
    return base.model_copy(update={"authz": result, "summary": summary})


def traffic_report(traffic: TrafficSummary) -> FindingsReport:
    base = report([zap_alert("9")])
    return base.model_copy(
        update={"coverage": base.coverage.model_copy(update={"traffic": traffic})}
    )


# ------------------------------------------------------------------ authz


def test_page_shows_each_authz_finding_with_its_technique_apart_from_zap() -> None:
    page = render_html(with_authz())

    assert "<h2>Autorização entre contas (técnica própria, determinística)</h2>" in page
    for technique in ("authz_horizontal", "authz_excessive_data", "authz_mass_assignment"):
        assert f"<code>{technique}</code>" in page
        assert TECHNIQUE_LABEL[technique] in page
    assert "não é achado do ZAP" in page
    assert "GET /api/x/{}" in page
    assert "senhaHash" in page


def test_page_summary_counts_authz_findings_in_their_own_cards() -> None:
    page = render_html(with_authz())

    assert "Autorização entre contas (técnica própria, não é do ZAP):" in page
    assert "Varredura ativa do ZAP:" in page
    assert "Autorização entre contas: estado completed, 3 achado(s), 2 item(ns)" in page


def test_page_says_authz_did_not_run_when_there_is_no_authz_json() -> None:
    page = render_html(report([zap_alert("9")]))

    assert "Autorização entre contas: não rodou" in page
    assert "<h2>Autorização entre contas" not in page


def test_page_lists_what_authz_could_not_test_with_the_reason() -> None:
    page = render_html(with_authz())

    assert "O que o teste de autorização não pôde testar (2)" in page
    assert "no_peer_account" in page
    assert "Cadastre outra conta." in page
    assert "Limites desta técnica" in page


def test_page_with_authz_but_no_zap_findings_does_not_say_there_is_no_finding() -> None:
    base = with_authz()
    empty = base.model_copy(update={"findings": (), "groups": ()})

    page = render_html(empty)

    assert "Nenhum achado da varredura do ZAP." in page
    assert "<code>authz_horizontal</code>" in page


def test_next_steps_cover_authz_findings_and_not_tested_items() -> None:
    steps = " ".join(next_steps(with_authz()))

    assert "achado(s) de autorização entre contas de gravidade ALTA" in steps
    assert "não pôde testar 2 item(ns)" in steps
    assert "ampli" not in steps.replace("sem ampliar", "")


def test_next_steps_warn_when_authz_stopped_early() -> None:
    steps = " ".join(next_steps(with_authz(status="scan_error", stop_message="ZAP caiu")))

    assert "parou antes do fim" in steps


def test_authz_findings_alone_do_not_trigger_the_nothing_found_step() -> None:
    base = with_authz()
    steps = " ".join(next_steps(base.model_copy(update={"findings": (), "groups": ()})))

    assert "Nenhum achado não é prova" not in steps
    assert "Nenhum achado não é prova" in " ".join(next_steps(report([])))


def test_hostile_authz_text_cannot_become_markup_and_secrets_are_redacted() -> None:
    base = with_authz()
    hostile = base.authz.findings[0].model_copy(  # type: ignore[union-attr]
        update={
            "title": XSS,
            "evidence": f"{XSS} token={JWT}",
            "fields": (XSS,),
            "operation_id": XSS,
            "actor_account": XSS,
        }
    )
    result = base.authz.model_copy(  # type: ignore[union-attr]
        update={
            "findings": (hostile,),
            "accounts": (XSS,),
            "not_tested": (
                base.authz.not_tested[0].model_copy(update={"message": XSS, "reason": XSS}),  # type: ignore[union-attr]
            ),
        }
    )

    page = render_html(base.model_copy(update={"authz": result}))

    parsed = parse(page)
    assert "script" not in parsed.tags
    assert "img" not in parsed.tags
    assert not any(name.startswith("on") for name, _ in parsed.attrs)
    assert "&lt;script&gt;" in page
    assert JWT not in page


def test_markdown_summary_also_counts_authz_findings() -> None:
    text = render_markdown(with_authz())

    assert "Autorização entre contas (técnica própria, não é do ZAP)" in text
    assert "| Alta | 3 |" in text


def test_authz_by_severity_is_filled_by_the_report_builder() -> None:
    ops = [operation("obter", "GET", "/users/v1/{username}")]

    built = assemble_report(
        probe=probe_result(ops),
        scan=scan_result([entry("obter", "GET", "/users/v1/{username}", 4, alert_ids=("9",))]),
        raw_alerts=[zap_alert("9")],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="2026-11-13T06:00:00+00:00",
        harness_version="0.0-test",
        auth_header=None,
        csrf_header=None,
        authz=authz_result(),
    )

    assert built.summary.authz_by_severity["high"] == 3
    assert built.summary.total == 1  # o total e by_severity continuam sendo só do ZAP
    assert report([zap_alert("9")]).summary.authz_by_severity == {}


# ------------------------------------------------------------------ cerca


def _wide() -> TrafficSummary:
    return TrafficSummary(
        enabled=True,
        allowed=40,
        denied=60,
        denied_by_reason={"malformed_request": 50, "deny_path": 10},
        denied_by_detail={"path_encoded_slash": 30, "path_matrix_param": 20, "deny_path": 10},
        path_shape_denied=50,
        allowed_outside_allow=7,
        path_mode="wide",
        duration_seconds=60.0,
        average_rps=1.0,
        peak_rps=2,
        limit_rps=5.0,
    )


def test_page_shows_the_mode_with_a_human_name_and_the_wide_note() -> None:
    page = render_html(traffic_report(_wide()))

    assert "Modo de leitura do caminho no proxy: wide (modo amplo, autorizado na carta" in page
    assert "7 pedido(s) liberados têm uma leitura do caminho fora de scope.allow" in page


def test_page_shows_human_names_beside_each_refusal_code() -> None:
    page = render_html(traffic_report(_wide()))

    assert (
        "<td>barra codificada no caminho (%2f)</td><td><code>path_encoded_slash</code></td>" in page
    )
    assert "<td>caminho proibido na carta (deny_paths)</td><td><code>deny_path</code></td>" in page


def test_page_warns_that_path_injection_coverage_was_partial() -> None:
    page = render_html(traffic_report(_wide()))

    assert "cobertura de injeção em segmento de caminho foi PARCIAL" in page
    assert "50 de 100 pedido(s) (50%)" in page


def test_strict_mode_warning_says_only_the_owner_can_authorize_wide() -> None:
    strict = _wide().model_copy(update={"path_mode": "strict", "allowed_outside_allow": 0})

    warning = path_shape_warning(strict)

    assert warning is not None
    assert "só o dono do produto pode autorizar wide na carta" in warning
    assert "o agente não liga esse modo" in warning


def test_old_scan_json_without_detail_falls_back_to_the_grouped_reason() -> None:
    old = TrafficSummary(enabled=True, allowed=1, denied=2, denied_by_reason={"deny_path": 2})

    assert denied_rows(old) == (("caminho proibido na carta (deny_paths)", "deny_path", 2),)


def test_unknown_code_is_shown_as_it_came() -> None:
    assert label_for("codigo_novo") == "codigo_novo"


@pytest.mark.parametrize("reason", list(ScopeReason))
def test_every_scope_reason_has_a_human_label(reason: ScopeReason) -> None:
    assert reason.value in SCOPE_CODE_LABELS
