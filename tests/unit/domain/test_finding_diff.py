import pytest
from pydantic import ValidationError

from harness_dast.domain.finding_diff import RetestResult, RetestStatus, classify_retest
from tests.fakes.verification_data import finding


@pytest.mark.parametrize(
    ("present", "operation_id", "expected"),
    [
        (True, "otherOperation", "reproduced"),
        (False, "coveredOperation", "not_reproduced"),
        (False, "otherOperation", "not_tested"),
        (False, None, "not_tested"),
    ],
)
def test_classifies_finding_using_fingerprint_and_coverage(
    present: bool, operation_id: str | None, expected: RetestStatus
) -> None:
    previous = finding().model_copy(update={"operation_id": operation_id})
    current = [finding()] if present else [finding().model_copy(update={"fingerprint": "b" * 64})]

    result = classify_retest([previous], current, {"coveredOperation"})

    assert result == (RetestResult(fingerprint=previous.fingerprint, result=expected),)


def test_returns_empty_when_no_previous_findings() -> None:
    assert classify_retest([], [], set()) == ()


def test_preserves_coverage_per_entry_when_previous_fingerprint_repeats() -> None:
    previous = finding().model_copy(update={"operation_id": "coveredOperation"})
    duplicate = previous.model_copy(update={"operation_id": "otherOperation"})

    results = classify_retest([previous, duplicate], [], {"coveredOperation"})

    assert [item.result for item in results] == ["not_reproduced", "not_tested"]


def test_returns_one_result_when_current_fingerprint_repeats() -> None:
    previous = finding()

    results = classify_retest([previous], [previous, previous], set())

    assert results == (RetestResult(fingerprint=previous.fingerprint, result="reproduced"),)


@pytest.mark.parametrize(
    "raw",
    ['{"fingerprint":"abc","result":"fixed"}', '{"fingerprint":"abc"}', '{"result":'],
)
def test_rejects_invalid_retest_result_json(raw: str) -> None:
    with pytest.raises(ValidationError):
        RetestResult.model_validate_json(raw)
