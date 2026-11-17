"""Do catálogo de explicação para o painel: uma explicação por `finding_id`, texto fixo."""

from harness_dast.domain.authz.result import AuthzFinding, AuthzResult
from harness_dast.domain.finding_explain import catalog_entries
from harness_dast.domain.panel.catalog import build_explanations, to_panel_explanation, who_label
from tests.unit.domain.panel.helpers import findings_report
from tests.unit.domain.report_helpers import RUN_ID


def _authz_result() -> AuthzResult:
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
    return AuthzResult(
        run_id=RUN_ID,
        product="vampi",
        status="completed",
        started_at="2026-11-13T05:20:00+00:00",
        finished_at="2026-11-13T05:21:00+00:00",
        findings=(finding,),
    )


def test_each_zap_finding_gets_the_catalog_explanation_of_its_rule() -> None:
    report = findings_report()

    got = build_explanations(report, None)

    explanation = got[report.findings[0].finding_id]
    assert explanation.title.startswith("Um texto digitado pode estar virando parte do comando")
    assert explanation.technical_name == "Injeção de SQL (CWE-89)"
    assert explanation.what_happened
    assert explanation.why_it_matters


def test_the_steps_say_who_does_each_one_in_the_words_of_the_screen() -> None:
    report = findings_report()

    explanation = build_explanations(report, None)[report.findings[0].finding_id]

    assert explanation.actions[0].who == "Você (QA)"
    assert "Time de dev" in {step.who for step in explanation.actions}
    assert explanation.what_to_do == " ".join(step.text for step in explanation.actions)
    assert explanation.who == "Time de dev"


def test_authorization_findings_get_the_explanation_of_their_technique() -> None:
    authz = _authz_result()

    got = build_explanations(None, authz)

    assert set(got) == {item.finding_id for item in authz.findings}
    assert all(item.actions for item in got.values())


def test_without_findings_the_result_is_empty() -> None:
    assert build_explanations(None, None) == {}


def test_who_label_covers_the_three_roles() -> None:
    assert who_label("QA") == "Você (QA)"
    assert who_label("dono do produto") == "Dono do produto"
    assert who_label("time de desenvolvimento") == "Time de dev"


def test_every_catalog_entry_converts_without_saying_safe_or_approved() -> None:
    for entry in catalog_entries():
        converted = to_panel_explanation(entry)
        text = f"{converted.title} {converted.what_happened} {converted.what_to_do}".lower()
        assert converted.actions
        assert "seguro" not in text.replace("segurança", "")
        assert "aprovado" not in text


def test_an_unknown_rule_gets_the_honest_generic_text_and_never_raises() -> None:
    report = findings_report(alerts=[])
    odd = (
        findings_report()
        .findings[0]
        .model_copy(update={"plugin_id": "999999", "title": "Regra nova <b>x</b>"})
    )
    odd = odd.model_copy(
        update={"classification": odd.classification.model_copy(update={"cwe": None})}
    )

    got = build_explanations(report.model_copy(update={"findings": (odd,)}), None)

    assert "não temos explicação simples" in got[odd.finding_id].what_happened
