"""Triagem: validação estrita e mesclagem que nunca apaga nem muda a severidade."""

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import Classification, Finding, FindingEvidence
from harness_dast.domain.triage import merge_triage, parse_triage
from harness_dast.domain.zap_alert import Severity

FP_A = "a" * 64
FP_B = "b" * 64


def finding(fingerprint: str, severity: Severity = "high", title: str = "SQL Injection") -> Finding:
    return Finding(
        finding_id=f"F-{fingerprint[:8]}",
        fingerprint=fingerprint,
        title=title,
        plugin_id="40018",
        alert_ref="40018",
        classification=Classification(cwe=89),
        proposed_severity=severity,
        proposed_confidence="low",
        method="GET",
        path_template="/x",
        attribution="source_message",
        occurrences=1,
        evidence=FindingEvidence(),
    )


def valid(*annotations: dict[str, object]) -> object:
    return {"schema_version": 1, "annotations": list(annotations)}


def test_merge_adds_notes_without_changing_anything_else() -> None:
    findings = (finding(FP_A), finding(FP_B, severity="low"))
    triage = parse_triage(
        valid({"fingerprint": FP_A, "note": "parece real", "suspected_false_positive": False})
    )

    merged, orphans = merge_triage(findings, triage)

    assert orphans == ()
    assert len(merged) == len(findings)
    assert [f.fingerprint for f in merged] == [f.fingerprint for f in findings]
    assert merged[0].triage is not None
    assert merged[0].triage.note == "parece real"
    assert merged[1].triage is None
    for before, after in zip(findings, merged, strict=True):
        assert after.model_copy(update={"triage": None}) == before
        assert after.proposed_severity == before.proposed_severity
        assert after.status == "needs_triage"


def test_suspected_false_positive_does_not_remove_or_downgrade_the_finding() -> None:
    triage = parse_triage(
        valid({"fingerprint": FP_A, "suspected_false_positive": True, "reason": "resposta JSON"})
    )

    merged, _ = merge_triage((finding(FP_A),), triage)

    assert len(merged) == 1
    assert merged[0].proposed_severity == "high"
    assert merged[0].triage is not None
    assert merged[0].triage.suspected_false_positive is True


def test_orphan_annotations_are_reported_and_ignored() -> None:
    triage = parse_triage(valid({"fingerprint": FP_B, "note": "n"}))

    merged, orphans = merge_triage((finding(FP_A),), triage)

    assert orphans == (FP_B,)
    assert merged[0].triage is None


def test_hostile_control_characters_in_notes_are_stripped() -> None:
    triage = parse_triage(valid({"fingerprint": FP_A, "note": "ok\x1b[31m‮ fim"}))

    merged, _ = merge_triage((finding(FP_A),), triage)

    assert merged[0].triage is not None
    assert "\x1b" not in merged[0].triage.note
    assert "‮" not in merged[0].triage.note


@pytest.mark.parametrize(
    "extra",
    [
        {"severity": "low"},
        {"proposed_severity": "informational"},
        {"delete": True},
        {"status": "closed"},
        {"remove": True},
    ],
)
def test_the_contract_has_no_way_to_change_severity_status_or_delete(
    extra: dict[str, object],
) -> None:
    with pytest.raises(ConfigError, match="campo não permitido"):
        parse_triage(valid({"fingerprint": FP_A, **extra}))


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"schema_version": 2, "annotations": []},
        {"schema_version": 1},
        {"schema_version": 1, "annotations": "x"},
        valid({"fingerprint": "curto"}),
        valid({"fingerprint": FP_A.upper()}),
        valid({"fingerprint": FP_A, "suspected_false_positive": True}),
        valid({"fingerprint": FP_A, "note": "x" * 501}),
        valid({"fingerprint": FP_A}, {"fingerprint": FP_A}),
        valid({"note": "sem fingerprint"}),
        valid({"fingerprint": FP_A, "suspected_false_positive": "sim", "reason": "r"}),
    ],
)
def test_invalid_or_malformed_triage_is_a_config_error_that_does_not_echo_values(
    data: object,
) -> None:
    with pytest.raises(ConfigError) as info:
        parse_triage(data)

    assert "triage.json" in info.value.message
    assert "curto" not in info.value.message
    assert info.value.hint


def test_too_many_annotations_are_refused() -> None:
    many: list[dict[str, object]] = [{"fingerprint": f"{i:064x}"} for i in range(5001)]

    with pytest.raises(ConfigError):
        parse_triage(valid(*many))
