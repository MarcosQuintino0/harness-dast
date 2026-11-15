"""Achado do teste negativo: fingerprint estável, sem o valor enviado (ADR 0051)."""

import pytest

from harness_dast.domain.negative_findings import build_negative_finding, negative_fingerprint
from harness_dast.domain.negative_plan import NegativeCase
from harness_dast.domain.negative_result import Location, NegativeFinding, NegativeResult
from harness_dast.domain.negative_values import CaseClass
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.negative_rig import CREATE, LIST, UPDATE

SECRET_VALUE = "valor-enviado-que-nao-pode-vazar"  # noqa: S105 - sentinela de teste


def make_case(
    base: ExchangeRecord = LIST,
    field: str = "limite",
    klass: CaseClass = "wrong_type",
    location: Location = "query",
    value: str = SECRET_VALUE,
) -> NegativeCase:
    return NegativeCase(base, location, field, klass, "minimum 1", value)


def build(case: NegativeCase | None = None, status: int = 200) -> NegativeFinding:
    return build_negative_finding(
        product="agenda",
        technique="input_accepted",
        case=case or make_case(),
        status=status,
        restored=None,
        created=False,
    )


def fingerprint(
    product: str = "agenda",
    technique: str = "input_accepted",
    case: NegativeCase | None = None,
) -> str:
    return negative_fingerprint(
        product=product,
        technique=technique,  # type: ignore[arg-type]  # o teste varia a técnica por texto
        case=case or make_case(),
    )


def test_the_fingerprint_is_stable_and_the_id_comes_from_it() -> None:
    finding = build()

    assert fingerprint() == fingerprint()
    assert len(fingerprint()) == 64
    assert finding.finding_id == f"N-{fingerprint()[:8]}"
    assert finding.fingerprint == fingerprint()
    assert finding.fingerprint_version == 1


@pytest.mark.parametrize(
    "changed",
    [
        lambda: fingerprint(product="outro"),
        lambda: fingerprint(technique="input_server_error"),
        lambda: fingerprint(case=make_case(field="ordem")),
        lambda: fingerprint(case=make_case(klass="below_minimum")),
        lambda: fingerprint(case=make_case(location="body")),
        lambda: fingerprint(case=make_case(base=CREATE, field="nome", location="body")),
        lambda: fingerprint(case=make_case(base=UPDATE, field="nome", location="body")),
    ],
)
def test_the_fingerprint_changes_with_each_part_it_is_made_of(changed: object) -> None:
    assert changed() != fingerprint()  # type: ignore[operator]  # o parâmetro é um chamável


def test_the_fingerprint_ignores_status_value_and_restoration() -> None:
    other_status = build_negative_finding(
        product="agenda",
        technique="input_accepted",
        case=make_case(),
        status=204,
        restored=True,
        created=True,
    )

    assert other_status.fingerprint == fingerprint()
    assert fingerprint(case=make_case(value="outro-valor")) == fingerprint()


def test_the_finding_carries_the_contract_limit_and_never_the_sent_value() -> None:
    finding = build()

    assert SECRET_VALUE not in finding.model_dump_json()
    assert finding.declared == "minimum 1"
    assert finding.field == "limite"
    assert finding.origin == "negative"
    assert finding.status == "needs_triage"
    assert finding.baseline_status == 200


def test_the_evidence_sentence_has_no_sent_value_and_names_the_field() -> None:
    finding = build(status=204)

    assert "'limite'" in finding.evidence
    assert "204" in finding.evidence
    assert SECRET_VALUE not in finding.evidence
    assert SECRET_VALUE not in finding.description + finding.solution + finding.title


def test_cwe_and_title_follow_the_technique() -> None:
    crashed = build_negative_finding(
        product="agenda",
        technique="input_server_error",
        case=make_case(),
        status=500,
        restored=None,
        created=False,
    )

    assert (build().cwe, crashed.cwe) == (20, 755)
    assert "aceito" in build().title
    assert "erro do servidor" in crashed.title
    assert crashed.proposed_severity == "low"


def test_a_write_finding_is_medium_and_remembers_restore_and_creation() -> None:
    finding = build_negative_finding(
        product="agenda",
        technique="input_accepted",
        case=make_case(base=UPDATE, field="preco", klass="below_minimum", location="body"),
        status=200,
        restored=False,
        created=False,
    )

    assert finding.proposed_severity == "medium"
    assert finding.restored is False


def test_the_result_model_has_no_field_for_a_sent_value() -> None:
    names = set(NegativeResult.model_fields)

    assert not {"value", "values", "sent_value", "payload"} & names
