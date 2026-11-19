import json

import pytest
from pydantic import ValidationError

from harness_dast.domain.nuclei_manifest import NucleiManifest, NucleiTemplateEntry
from harness_dast.domain.nuclei_version import (
    NUCLEI_VERSION,
    TEMPLATES_ARCHIVE_SHA256,
    TEMPLATES_VERSION,
)


def _entry() -> dict[str, object]:
    return {
        "path": "http/technologies/example.yaml",
        "sha256": "a" * 64,
        "protocols": ["http"],
        "methods": ["GET", "M-SEARCH"],
        "raw": True,
        "unsafe": False,
        "code": False,
        "headless": False,
        "oast": False,
        "dast": False,
        "unparsed_method": False,
        "tags": ["detect"],
        "severity": "info",
        "category": "technologies",
    }


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "nuclei_version": NUCLEI_VERSION,
        "templates_version": TEMPLATES_VERSION,
        "templates_archive_sha256": TEMPLATES_ARCHIVE_SHA256,
        "entries": [_entry()],
    }


def test_accepts_manifest_quando_metadata_matches_pinned_catalog() -> None:
    manifest = NucleiManifest.model_validate_json(json.dumps(_manifest()))

    assert manifest.entries[0].methods == ("GET", "M-SEARCH")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sha256", "g" * 64),
        ("path", "http/technologies/../example.yaml"),
        ("path", "/http/technologies/example.yaml"),
        ("path", "C:/http/technologies/example.yaml"),
        ("path", "http\\technologies\\example.yaml"),
        ("methods", ["get"]),
        ("methods", "GET"),
        ("unsafe", "false"),
        ("severity", "invalid"),
        ("category", "exposures"),
        ("unexpected", True),
    ],
)
def test_rejects_entry_quando_metadata_is_invalid(field: str, value: object) -> None:
    entry = _entry() | {field: value}

    with pytest.raises(ValidationError):
        NucleiTemplateEntry.model_validate(entry)


def test_rejects_entry_quando_method_audit_flag_is_missing() -> None:
    entry = _entry()
    del entry["unparsed_method"]

    with pytest.raises(ValidationError, match="unparsed_method"):
        NucleiTemplateEntry.model_validate(entry)


def test_accepts_entry_quando_path_has_no_http_category() -> None:
    entry = NucleiTemplateEntry.model_validate(
        _entry() | {"path": "dns/example.yaml", "category": None, "protocols": ["dns"]}
    )

    assert entry.category is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("nuclei_version", "0.0.0"),
        ("templates_version", "0.0.0"),
        ("templates_archive_sha256", "f" * 64),
        ("extra", 1),
    ],
)
def test_rejects_manifest_quando_top_level_field_is_invalid(field: str, value: object) -> None:
    data = _manifest() | {field: value}

    with pytest.raises(ValidationError, match=field):
        NucleiManifest.model_validate(data)


def test_rejects_manifest_quando_entries_are_missing() -> None:
    data = _manifest()
    del data["entries"]

    with pytest.raises(ValidationError, match="entries"):
        NucleiManifest.model_validate(data)


def test_rejects_manifest_quando_entry_path_is_repeated() -> None:
    data = _manifest() | {"entries": [_entry(), _entry()]}

    with pytest.raises(ValidationError, match="caminhos de modelos duplicados"):
        NucleiManifest.model_validate(data)


def test_rejects_manifest_quando_json_is_malformed() -> None:
    with pytest.raises(ValidationError, match="json_invalid"):
        NucleiManifest.model_validate_json('{"entries": [')


@pytest.mark.parametrize("field", ["entries", "schema_version"])
def test_rejects_manifest_change_quando_field_is_replaced(field: str) -> None:
    manifest = NucleiManifest.model_validate(_manifest())

    with pytest.raises(ValidationError, match="frozen_instance"):
        setattr(manifest, field, None)
