import json

import pytest
from pydantic import ValidationError

from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.nuclei_findings import (
    NucleiFinding,
    NucleiResultRecord,
    TechnologyDetected,
    classify,
    group_findings,
    parse_nuclei_jsonl,
)


def _line(**overrides: object) -> dict[str, object]:
    return {
        "template-id": "example-config",
        "template-path": "http/exposures/example.yaml",
        "type": "http",
        "host": "https://example.invalid",
        "method": "GET",
        "matched-at": "https://example.invalid/config",
        "info": {"severity": "low"},
    } | overrides


def _finding(**overrides: object) -> NucleiFinding:
    result = classify(NucleiResultRecord.from_data(_line(**overrides)))
    assert isinstance(result, NucleiFinding)
    return result


def test_discards_content_quando_raw_jsonl_contains_synthetic_markers() -> None:
    raw = _line(
        **{
            "curl-command": "MARCADOR_CURL",
            "request": "MARCADOR_PEDIDO",
            "response": "MARCADOR_RESPOSTA",
            "extracted-results": ["MARCADOR_EXTRAÍDO", "ç"],
            "host": "https://example.invalid:443/MARCADOR_CAMINHO_HOST?MARCADOR_HOST",
            "matched-at": "https://example.invalid/config?MARCADOR_CONSULTA#MARCADOR_FRAGMENTO",
            "matcher-name": "expected",
            "info": {"severity": "low", "metadata": "MARCADOR_INFO"},
            "extracted_count": 999,
            "extra": "MARCADOR_EXTRA",
        }
    )

    record = parse_nuclei_jsonl(json.dumps(raw))

    assert record.model_dump() == {
        "template_id": "example-config",
        "template_path": "http/exposures/example.yaml",
        "severity": "low",
        "type": "http",
        "host": "example.invalid:443",
        "method": "GET",
        "matched_path": "/config",
        "matcher_name": "expected",
        "extracted_count": 2,
        "extracted_bytes": len("MARCADOR_EXTRAÍDOç".encode()),
    }
    serialized = record.model_dump_json()
    assert "MARCADOR_" not in serialized
    assert all(
        f'"{key}"' not in serialized
        for key in ("curl-command", "request", "response", "extracted-results")
    )


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("critical", "high"),
        ("high", "high"),
        ("medium", "medium"),
        ("low", "low"),
        ("info", "informational"),
        ("unknown", "informational"),
        ("custom", "informational"),
    ],
)
def test_maps_severity_quando_result_has_nuclei_rating(severity: str, expected: str) -> None:
    finding = _finding(info={"severity": severity})

    assert finding.proposed_severity == expected


def test_groups_findings_quando_only_origin_query_and_encoding_differ() -> None:
    first = _finding()
    second = _finding(**{"matched-at": "https://another.invalid/%63onfig/?v=1"})

    grouped = group_findings((first, first, second))

    assert grouped == (first.model_copy(update={"occurrences": 3}),)
    assert first.fingerprint == "594d4ec47c584c5dc488282296f110eb9f9f617a0e5cb0e2488b9df70f06268f"
    assert first.finding_id == f"U-{first.fingerprint[:8]}"
    assert first.origin == "nuclei"


@pytest.mark.parametrize(
    "override", [{"template-id": "different"}, {"method": "HEAD"}, {"matched-at": "/other"}]
)
def test_changes_fingerprint_quando_identity_field_changes(override: dict[str, object]) -> None:
    first = _finding()
    second = _finding(**override)

    assert first.fingerprint != second.fingerprint


def test_keeps_strongest_rating_quando_duplicate_has_higher_severity() -> None:
    high = _finding(info={"severity": "high"})
    low = _finding(info={"severity": "low"})

    grouped = group_findings((high, low))

    assert grouped == (high.model_copy(update={"occurrences": 2}),)


@pytest.mark.parametrize(
    "override",
    [
        {"template-path": "http/technologies/example.yaml"},
        {"template-path": "/catalog/http/technologies/example.yaml"},
        {"type": "detection"},
    ],
)
def test_classifies_technology_quando_result_is_informational_detection(
    override: dict[str, object],
) -> None:
    record = NucleiResultRecord.from_data(_line(info={"severity": "info"}, **override))

    assert classify(record) == TechnologyDetected(record=record)


def test_classifies_finding_quando_technology_metadata_has_noninformational_severity() -> None:
    finding = _finding(**{"template-path": "http/technologies/example.yaml"})

    assert finding.proposed_severity == "low"


def test_preserves_missing_method_quando_jsonl_omits_method() -> None:
    raw = _line()
    del raw["method"]

    result = NucleiResultRecord.from_data(raw)

    assert result.method is None


def test_preserves_encoded_delimiters_quando_path_contains_query_like_text() -> None:
    result = NucleiResultRecord.from_data(_line(**{"matched-at": "/config%3Fkey%23value?gone"}))

    assert result.matched_path == "/config%3Fkey%23value"


def test_reports_invalid_jsonl_quando_line_is_malformed() -> None:
    with pytest.raises(ExternalToolError, match="JSONL do Nuclei malformada") as raised:
        parse_nuclei_jsonl('{"request": "MARCADOR_PRIVADO"')

    assert "MARCADOR_PRIVADO" not in str(raised.value)


def test_reports_missing_field_quando_required_metadata_is_absent() -> None:
    raw = _line()
    del raw["template-id"]

    with pytest.raises(ExternalToolError, match=r"template_id.*campo obrigatório ausente"):
        NucleiResultRecord.from_data(raw)


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"matched-at": "https://example.invalid/../MARCADOR_PRIVADO"}, "matched_path"),
        ({"host": "https://user:MARCADOR_PRIVADO@example.invalid"}, "host"),
        ({"extracted-results": {"secret": "MARCADOR_PRIVADO"}}, "extracted-results"),
        ({"info": "MARCADOR_PRIVADO"}, "info"),
    ],
)
def test_reports_field_without_echo_quando_metadata_is_invalid(
    override: dict[str, object], field: str
) -> None:
    with pytest.raises(ExternalToolError, match=field) as raised:
        NucleiResultRecord.from_data(_line(**override))

    assert "MARCADOR_PRIVADO" not in str(raised.value)


@pytest.mark.parametrize("field", ["severity", "method"])
def test_rejects_record_change_quando_field_is_reassigned(field: str) -> None:
    record = NucleiResultRecord.from_data(_line())

    with pytest.raises(ValidationError, match="frozen_instance"):
        setattr(record, field, None)
