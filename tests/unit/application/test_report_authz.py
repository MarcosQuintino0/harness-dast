"""`report` com `authz.json`: seção própria, técnica de cada achado, gate e honestidade."""

import pytest

from harness_dast.application.report import ReportRequest, exceeds
from harness_dast.domain.authz.findings import (
    excessive_data_finding,
    horizontal_finding,
    mass_assignment_finding,
)
from harness_dast.domain.authz.findings_access import anonymous_finding, tampered_finding
from harness_dast.domain.authz.findings_write import horizontal_write_finding
from harness_dast.domain.authz.result import AuthzNotTested, AuthzResult, CheckSummary
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.report.markdown import render_markdown
from harness_dast.domain.report.model import (
    NOT_TESTED_STATEMENTS,
    NOT_TESTED_WITH_AUTHZ,
    FindingsReport,
    build_digest,
)
from tests.fakes.scan_rig import ScanRig
from tests.unit.application.test_report import scanned


def authz_result(
    product: str = "agenda", run_id: str = "x", *, findings: bool = True
) -> AuthzResult:
    items = (
        (
            horizontal_finding(
                product=product,
                operation_id="ver",
                method="GET",
                path_template="/api/x/{id}",
                actor=("b", "paciente"),
                owner=("a", "paciente"),
                statuses=(200, 200),
            ),
            excessive_data_finding(
                product=product,
                operation_id="lista",
                method="GET",
                path_template="/api/y",
                actor=("adm", "admin"),
                status=200,
                fields=("items[].passwordHash",),
            ),
            mass_assignment_finding(
                product=product,
                operation_id="up",
                method="PUT",
                path_template="/api/me",
                actor=("a", "paciente"),
                sent_field="role",
                changed=("papel",),
                status=200,
                restored=True,
            ),
        )
        if findings
        else ()
    )
    return AuthzResult(
        run_id=run_id,
        product=product,
        status="completed",
        started_at="a",
        finished_at="b",
        requests_sent=7,
        accounts=("a", "b"),
        checks=(
            CheckSummary(
                check="horizontal", status="completed", candidates=1, tested=1, findings=1
            ),
            CheckSummary(check="vertical", status="skipped", message="x"),
        ),
        findings=items,
        not_tested=(
            AuthzNotTested(
                check="vertical",
                reason="no_role_order",
                message="Declare authz.role_order.",
            ),
            AuthzNotTested(
                check="horizontal",
                operation_id="o",
                method="GET",
                path="/api/z/{id}",
                reason="no_peer_account",
                message="Cadastre outra conta.",
            ),
        ),
    )


def report_with(rig: ScanRig, authz: AuthzResult | None) -> FindingsReport:
    run_id = rig.probe_result.run_id
    if authz is not None:
        rig.artifacts.authz[run_id] = authz
    return rig.report().execute(ReportRequest(product="agenda", run_id=run_id)).report


def test_the_report_carries_the_authz_section_separate_from_the_zap_findings() -> None:
    rig = scanned()

    report = report_with(rig, authz_result())

    assert len(report.findings) == 1
    assert {f.technique for f in report.findings} == {"zap_active_scan"}
    assert report.authz is not None
    assert {f.technique for f in report.authz.findings} == {
        "authz_horizontal",
        "authz_excessive_data",
        "authz_mass_assignment",
    }
    assert all(f.origin == "authz" for f in report.authz.findings)


def test_without_authz_the_report_is_unchanged() -> None:
    rig = scanned()

    report = report_with(rig, None)

    assert report.authz is None
    assert report.not_tested_statements == NOT_TESTED_STATEMENTS


def test_with_authz_the_honesty_statements_describe_what_it_covered() -> None:
    report = report_with(scanned(), authz_result(findings=False))

    assert report.not_tested_statements == NOT_TESTED_WITH_AUTHZ
    assert "authz" in report.not_tested_statements[0]
    assert "NÃO é evidência" in report.not_tested_statements[-1]


def test_the_markdown_names_the_technique_of_every_finding() -> None:
    report = report_with(scanned(), authz_result())

    text = render_markdown(report)

    assert "## Autorização entre contas" in text
    assert "authz_horizontal" in text
    assert "authz_excessive_data" in text
    assert "authz_mass_assignment" in text
    assert "varredura ativa do ZAP" in text
    assert "Declare authz" in text
    assert "passwordHash" in text
    assert "Limites desta técnica" in text


def test_the_markdown_without_authz_has_no_authz_section() -> None:
    text = render_markdown(report_with(scanned(), None))

    assert "Autorização entre contas" not in text


def test_the_gate_counts_authz_findings_even_when_the_zap_found_nothing() -> None:
    rig = scanned(risk="Low")
    quiet = report_with(rig, authz_result(findings=False))
    loud = report_with(rig, authz_result())

    assert exceeds(quiet, "high") is False
    assert exceeds(loud, "high") is True
    assert exceeds(loud, "none") is False


def test_the_digest_exposes_the_authz_result() -> None:
    report = report_with(scanned(), authz_result())

    digest = build_digest(report, ("findings.json",), "none", exceeds=False)

    assert digest.authz is not None
    assert len(digest.authz.findings) == 3


def test_an_authz_json_of_another_product_is_refused() -> None:
    rig = scanned()
    rig.artifacts.authz[rig.probe_result.run_id] = authz_result(product="outro")

    with pytest.raises(ConfigError, match="outro produto"):
        rig.report().execute(ReportRequest(product="agenda", run_id=rig.probe_result.run_id))


def test_no_value_of_a_suspect_field_reaches_the_report() -> None:
    report = report_with(scanned(), authz_result())

    text = report.model_dump_json() + render_markdown(report)

    assert "$2b$" not in text


def access_result() -> AuthzResult:
    base = authz_result(findings=False)
    findings = (
        anonymous_finding(
            product="agenda",
            operation_id="lista",
            method="GET",
            path_template="/api/y",
            actor=("adm", "admin"),
            operation=None,
            statuses=(200, 200),
        ),
        tampered_finding(
            product="agenda",
            operation_id="lista",
            method="GET",
            path_template="/api/y",
            actor=("adm", "admin"),
            variants=("alg_none", "scrambled"),
            statuses=(200, 200),
        ),
    )
    return base.model_copy(update={"findings": findings})


def test_the_markdown_shows_the_access_findings_with_label_and_variants_but_no_token() -> None:
    report = report_with(scanned(), access_result())

    text = render_markdown(report)

    assert "Acesso sem login" in text
    assert "Token adulterado aceito" in text
    assert "`authz_anonymous_access`" in text
    assert "`alg_none`" in text
    assert "CWE-347" in text
    assert "eyJ" not in text


def test_the_findings_json_carries_the_access_techniques_and_variants() -> None:
    report = report_with(scanned(), access_result())

    assert report.authz is not None
    dumped = report.model_dump(mode="json")["authz"]["findings"]
    assert {item["technique"] for item in dumped} == {
        "authz_anonymous_access",
        "authz_tampered_token",
    }
    assert [item["variants"] for item in dumped] == [[], ["alg_none", "scrambled"]]
    by_severity = report.summary.authz_by_severity
    assert (by_severity["high"], by_severity["medium"]) == (1, 1)


def derived_post_result() -> AuthzResult:
    base = authz_result(findings=False)
    finding = mass_assignment_finding(
        product="agenda",
        operation_id="criarMedico",
        method="POST",
        path_template="/api/medicos",
        actor=("adm", "admin"),
        sent_field="nivelAcesso",
        changed=("nivelAcesso",),
        status=201,
        restored=None,
        source="response_only",
        kind="privilege",
        observed_in="created_read",
    )
    return base.model_copy(update={"findings": (finding,), "created_resources": 3})


def test_the_markdown_shows_the_source_of_the_field_and_the_created_resources() -> None:
    text = render_markdown(report_with(scanned(), derived_post_result()))

    assert "**Origem do campo testado:** campo que o OpenAPI só mostra na resposta" in text
    assert "O teste criou 3 recurso(s) no ambiente de teste" in text
    assert "hdast cleanup" in text


def test_the_markdown_without_created_resources_has_no_such_line() -> None:
    text = render_markdown(report_with(scanned(), authz_result()))

    assert "O teste criou" not in text
    assert "Origem do campo testado" in text  # o declarado também diz de onde veio


def test_the_findings_json_carries_the_source_and_the_created_count() -> None:
    report = report_with(scanned(), derived_post_result())

    assert report.authz is not None
    dumped = report.model_dump(mode="json")["authz"]
    assert dumped["created_resources"] == 3
    assert dumped["findings"][0]["candidate_source"] == "response_only"
    assert dumped["findings"][0]["proposed_severity"] == "high"


def write_result() -> AuthzResult:
    finding = horizontal_write_finding(
        product="agenda",
        operation_id="salvarNota",
        method="PUT",
        path_template="/api/notas/{id}",
        actor=("b", "paciente"),
        owner=("a", "paciente"),
        status=200,
        field="titulo",
        restored=True,
    )
    return authz_result(findings=False).model_copy(
        update={
            "findings": (finding,),
            "checks": (
                CheckSummary(
                    check="horizontal_write", status="completed", candidates=1, tested=1, findings=1
                ),
            ),
        }
    )


def test_the_markdown_and_the_html_show_the_write_technique_and_the_field_name() -> None:
    from harness_dast.domain.authz.findings import TECHNIQUE_LABEL
    from harness_dast.domain.report.html import render_html

    report = report_with(scanned(), write_result())

    text = render_markdown(report)
    page = render_html(report)

    for output in (text, page):
        assert "authz_horizontal_write" in output
        assert TECHNIQUE_LABEL["authz_horizontal_write"].split(" (")[0] in output
        assert "titulo" in output
    assert "com identificador no caminho ou na consulta" in text


def test_the_findings_json_carries_the_write_technique_with_the_field() -> None:
    report = report_with(scanned(), write_result())

    assert report.authz is not None
    dumped = report.model_dump(mode="json")["authz"]["findings"][0]
    assert dumped["technique"] == "authz_horizontal_write"
    assert dumped["fields"] == ["titulo"]
    assert dumped["owasp_api_2023"].startswith("API1:2023")
