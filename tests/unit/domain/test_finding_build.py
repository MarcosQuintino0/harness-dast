"""Alerta do ZAP para achado: resolução pela mensagem aprendida, deduplicação e estabilidade."""

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from harness_dast.domain.finding import Finding
from harness_dast.domain.finding_build import (
    AlertResolver,
    OperationRef,
    build_findings,
    plain_text,
)
from harness_dast.domain.redaction import EvidenceMessage
from harness_dast.domain.zap_alert import RawAlert
from tests.fakes.zap_alerts import zap_alert

USER = OperationRef(operation_id="obter", method="GET", path="/users/v1/{username}")
BOOKS = OperationRef(operation_id="livros", method="GET", path="/books/v1/{title}")
ROOT = OperationRef(operation_id="raiz", method="GET", path="/users/v1")


def build(
    alerts: list[dict[str, str]],
    *,
    by_message: dict[int, OperationRef] | None = None,
    by_alert: dict[str, OperationRef] | None = None,
    operations: list[OperationRef] | None = None,
    evidence: dict[int, EvidenceMessage] | None = None,
) -> tuple[Finding, ...]:
    resolver = AlertResolver(
        {4: USER, 6: USER, 11: USER} if by_message is None else by_message,
        by_alert or {},
        [USER, BOOKS, ROOT] if operations is None else operations,
    )
    parsed = [RawAlert.model_validate(a) for a in alerts]
    return build_findings(parsed, product="vampi", resolver=resolver, evidence=evidence or {})


def test_alert_is_resolved_through_source_message_not_the_mutated_url() -> None:
    (finding,) = build([zap_alert(url="http://qualquer/coisa/mutada", sourceMessageId="4")])

    assert finding.operation_id == "obter"
    assert finding.path_template == "/users/v1/{}"
    assert finding.attribution == "source_message"
    assert finding.method == "GET"


def test_three_source_messages_of_the_same_defect_collapse_into_one_finding() -> None:
    alerts = [
        zap_alert("1", sourceMessageId="4", messageId="10"),
        zap_alert("2", sourceMessageId="6", messageId="11"),
        zap_alert("3", sourceMessageId="11", messageId="12"),
    ]

    findings = build(alerts)

    assert len(findings) == 1
    assert findings[0].occurrences == 3


def test_fingerprint_ignores_payload_host_ids_message_ids_and_severity() -> None:
    first = build([zap_alert("1", attack="'", url="http://a/x/1", messageId="10", risk="High")])
    second = build(
        [
            zap_alert(
                "99",
                attack="' OR 1=1 --",
                url="http://outro-host/y/2",
                messageId="55",
                risk="Low",
                confidence="High",
            )
        ]
    )

    assert first[0].fingerprint == second[0].fingerprint
    assert first[0].proposed_severity != second[0].proposed_severity


def test_fingerprint_changes_with_method_template_parameter_and_plugin() -> None:
    base = build([zap_alert()])[0].fingerprint
    other_parameter = build([zap_alert(param="username")])[0].fingerprint
    other_plugin = build([zap_alert(pluginId="40012", alertRef="40012-1")])[0].fingerprint
    other_template = build([zap_alert(sourceMessageId="7")], by_message={7: BOOKS})[0].fingerprint
    other_vector = build([zap_alert(inputVector="json")])[0].fingerprint
    post = OperationRef(operation_id="obter", method="POST", path="/users/v1/{username}")
    other_method = build([zap_alert()], by_message={4: post})[0].fingerprint

    assert (
        len({base, other_parameter, other_plugin, other_template, other_vector, other_method}) == 6
    )


def test_alert_scan_attribution_is_used_when_the_source_message_is_unknown() -> None:
    (finding,) = build([zap_alert("8", sourceMessageId="999")], by_alert={"8": BOOKS})

    assert (finding.operation_id, finding.attribution) == ("livros", "scan")


def test_url_match_resolves_a_unique_template_and_prefers_the_most_specific_one() -> None:
    generic = OperationRef(operation_id="g", method="GET", path="/users/{a}/{b}")
    specific = OperationRef(operation_id="s", method="GET", path="/users/v1/{username}")

    (finding,) = build(
        [zap_alert(sourceMessageId="", url="http://h/users/v1/alice")],
        by_message={},
        operations=[generic, specific],
    )

    assert (finding.operation_id, finding.attribution) == ("s", "url_match")


def test_ambiguous_url_match_stays_unresolved() -> None:
    a = OperationRef(operation_id="a", method="GET", path="/x/{p}")
    b = OperationRef(operation_id="b", method="GET", path="/x/{q}")

    (finding,) = build(
        [zap_alert(sourceMessageId="", url="http://h/x/1")], by_message={}, operations=[a, b]
    )

    assert finding.attribution == "unresolved"
    assert finding.operation_id is None
    assert finding.path_template == "/x/{}"


def test_unresolved_alert_still_becomes_a_finding_never_dropped() -> None:
    findings = build(
        [zap_alert(sourceMessageId="", url="http://h/nada/12345", method="POST")],
        by_message={},
        operations=[],
    )

    assert len(findings) == 1
    assert findings[0].method == "POST"


def test_zap_false_positive_confidence_is_still_a_finding() -> None:
    (finding,) = build([zap_alert(confidence="False Positive")])

    assert finding.proposed_confidence == "false_positive"
    assert finding.status == "needs_triage"


def test_best_occurrence_is_the_most_severe_then_most_confident_then_oldest() -> None:
    alerts = [
        zap_alert("5", risk="Low", confidence="High", sourceMessageId="4", messageId="500"),
        zap_alert("6", risk="High", confidence="Low", sourceMessageId="4", messageId="600"),
        zap_alert("7", risk="High", confidence="Medium", sourceMessageId="4", messageId="700"),
    ]
    evidence = {
        n: EvidenceMessage(message_id=n, request_header="GET http://h/ HTTP/1.1")
        for n in (500, 600, 700)
    }

    (finding,) = build(alerts, evidence=evidence)

    assert finding.evidence.message_id == 700
    assert finding.proposed_severity == "high"
    assert finding.proposed_confidence == "medium"


def test_evidence_falls_back_to_other_occurrences_then_to_the_alert_text() -> None:
    alerts = [
        zap_alert("1", messageId="10", sourceMessageId="4"),
        zap_alert("2", messageId="20", sourceMessageId="6"),
    ]
    only_second = {20: EvidenceMessage(message_id=20, request_header="GET http://h/x HTTP/1.1")}

    (with_fallback,) = build(alerts, evidence=only_second)
    (without,) = build(alerts)

    assert with_fallback.evidence.message_id == 20
    assert without.evidence.available is False
    assert without.evidence.zap_evidence == "HTTP/1.1 500 Internal Server Error"


def test_classification_uses_cwe_wasc_and_only_unambiguous_owasp_mapping() -> None:
    (sqli,) = build([zap_alert()])
    (ssrf,) = build([zap_alert(cweid="918")])

    assert sqli.classification.cwe == 89
    assert sqli.classification.wasc == 19
    assert sqli.classification.owasp_api_2023 is None
    assert ssrf.classification.owasp_api_2023 == "API7:2023 Server Side Request Forgery"


def test_findings_are_ordered_by_severity_then_confidence_then_title() -> None:
    alerts = [
        zap_alert("1", risk="Low", pluginId="1", alertRef="1", alert="B"),
        zap_alert("2", risk="High", pluginId="2", alertRef="2", alert="A"),
        zap_alert("3", risk="Medium", pluginId="3", alertRef="3", alert="C"),
        zap_alert("4", risk="High", confidence="High", pluginId="4", alertRef="4", alert="Z"),
    ]

    titles = [f.title for f in build(alerts)]

    assert titles == ["Z", "A", "C", "B"]


def test_html_and_control_text_from_zap_is_flattened() -> None:
    out = plain_text("<p>Olá &amp; <b>mundo</b></p>\x1b[31m\n  fim")

    assert out == "Olá & mundo fim"
    assert plain_text("x" * 5000, 100).endswith("…")


def test_alert_with_non_numeric_ids_does_not_break_resolution() -> None:
    (finding,) = build([zap_alert(sourceMessageId="abc", messageId="", cweid="-1", wascid="")])

    assert finding.classification.cwe is None
    assert finding.evidence.message_id is None


@given(st.lists(st.sampled_from(["1", "2", "3", "4"]), min_size=1, max_size=8))
def test_building_twice_gives_the_same_findings(ids: list[str]) -> None:
    alerts: list[Any] = [
        zap_alert(i, sourceMessageId="4", messageId=str(n)) for n, i in enumerate(ids)
    ]

    assert build(alerts) == build(list(alerts))


def test_alerts_that_differ_only_by_payload_collapse_into_one_finding() -> None:
    alerts = [
        zap_alert("1", attack="'", messageId="10"),
        zap_alert("2", attack="' OR 1=1 --", messageId="11"),
        zap_alert("3", attack='" OR ""="', messageId="12"),
    ]

    (finding,) = build(alerts)

    assert finding.occurrences == 3


def test_an_alert_from_an_alpha_or_beta_rule_becomes_an_experimental_finding() -> None:
    nosql = zap_alert("1", pluginId="40033", alertRef="40033", name="NoSQL Injection - MongoDB")
    sql = zap_alert("2")

    by_plugin = {item.plugin_id: item for item in build([nosql, sql])}

    assert by_plugin["40033"].experimental is True
    assert by_plugin["40018"].experimental is False


def test_the_experimental_mark_does_not_change_severity_or_fingerprint() -> None:
    plain = build([zap_alert("1", pluginId="40033", alertRef="40033")])[0]
    again = build([zap_alert("1", pluginId="40033", alertRef="40033")])[0]

    assert plain.proposed_severity == "high"
    assert plain.fingerprint == again.fingerprint
    assert plain.model_dump()["experimental"] is True
