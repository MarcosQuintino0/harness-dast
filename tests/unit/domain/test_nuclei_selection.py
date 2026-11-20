from typing import Any

import pytest

from harness_dast.domain.nuclei_manifest import (
    NucleiManifest,
    NucleiPermissions,
    NucleiTemplateEntry,
    NucleiVeto,
    select_templates,
    veto_reasons,
)
from harness_dast.domain.nuclei_version import (
    NUCLEI_VERSION,
    TEMPLATES_ARCHIVE_SHA256,
    TEMPLATES_VERSION,
)


def _entry(name: str = "a", **changes: Any) -> NucleiTemplateEntry:
    data: dict[str, Any] = {
        "path": f"http/misconfiguration/{name}.yaml",
        "sha256": "b" * 64,
        "protocols": ["http"],
        "methods": ["GET"],
        "raw": False,
        "unsafe": False,
        "code": False,
        "headless": False,
        "oast": False,
        "dast": False,
        "unparsed_method": False,
        "tags": ["exposure"],
        "severity": "low",
        "category": "misconfiguration",
    }
    data.update(changes)
    return NucleiTemplateEntry.model_validate(data)


def _manifest(*entries: NucleiTemplateEntry) -> NucleiManifest:
    return NucleiManifest(
        nuclei_version=NUCLEI_VERSION,
        templates_version=TEMPLATES_VERSION,
        templates_archive_sha256=TEMPLATES_ARCHIVE_SHA256,
        entries=entries,
    )


@pytest.mark.parametrize(
    ("changes", "veto"),
    [
        ({"protocols": ["http", "dns"]}, NucleiVeto.NON_HTTP),
        ({"protocols": ["tcp"]}, NucleiVeto.NON_HTTP),
        ({"protocols": []}, NucleiVeto.NON_HTTP),
        ({"unsafe": True}, NucleiVeto.UNSAFE),
        ({"code": True}, NucleiVeto.CODE),
        ({"headless": True}, NucleiVeto.HEADLESS),
        ({"oast": True}, NucleiVeto.OAST),
        ({"dast": True}, NucleiVeto.DAST),
        ({"unparsed_method": True}, NucleiVeto.UNPARSED_METHOD),
        ({"tags": ["dos"]}, NucleiVeto.TAG_DOS),
        ({"tags": ["intrusive"]}, NucleiVeto.TAG_INTRUSIVE),
        ({"tags": ["bruteforce"]}, NucleiVeto.TAG_BRUTEFORCE),
        ({"tags": ["fuzz"]}, NucleiVeto.TAG_FUZZ),
        ({"tags": ["default-logins"]}, NucleiVeto.TAG_DEFAULT_LOGINS),
    ],
)
def test_vetoes_entry_quando_a_reason_applies(changes: dict[str, Any], veto: NucleiVeto) -> None:
    assert veto_reasons(_entry(**changes)) == {veto}


def test_does_not_veto_quando_entry_is_clean() -> None:
    assert veto_reasons(_entry()) == frozenset()


def test_does_not_veto_raw_quando_the_method_was_parsed() -> None:
    assert veto_reasons(_entry(raw=True, methods=["GET", "POST"])) == frozenset()


def test_vetoes_raw_quando_the_method_is_unparsed() -> None:
    entry = _entry(raw=True, methods=[], unparsed_method=True)

    assert veto_reasons(entry) == {NucleiVeto.UNPARSED_METHOD}


def test_collects_every_reason_quando_several_apply() -> None:
    entry = _entry(unsafe=True, tags=["dos", "fuzz"])

    assert veto_reasons(entry) == {NucleiVeto.UNSAFE, NucleiVeto.TAG_DOS, NucleiVeto.TAG_FUZZ}


_MIXED = _manifest(
    _entry("read", methods=["GET", "HEAD"]),
    _entry("nomethod", methods=[]),
    _entry("write", methods=["POST"]),
    _entry("delete", methods=["DELETE"]),
    _entry("both", methods=["GET", "DELETE", "PUT"]),
    _entry("unknown", methods=["PROPFIND"]),
    _entry("vetoed", unsafe=True),
)


def _chosen(permissions: NucleiPermissions) -> set[str]:
    prefix = "http/misconfiguration/"
    paths = select_templates(_MIXED, permissions).paths
    return {p.removeprefix(prefix).removesuffix(".yaml") for p in paths}


@pytest.mark.parametrize(
    ("permissions", "expected"),
    [
        (NucleiPermissions(), {"read", "nomethod"}),
        (NucleiPermissions(writes=True), {"read", "nomethod", "write", "unknown"}),
        (NucleiPermissions(delete=True), {"read", "nomethod", "delete"}),
        (
            NucleiPermissions(writes=True, delete=True),
            {"read", "nomethod", "write", "delete", "both", "unknown"},
        ),
        (NucleiPermissions(writes=True, delete=True, login=True), {"read", "nomethod"}),
        (NucleiPermissions(login=True), {"read", "nomethod"}),
    ],
)
def test_selects_by_methods_quando_permissions_vary(
    permissions: NucleiPermissions, expected: set[str]
) -> None:
    assert _chosen(permissions) == expected


def test_counts_the_exclusion_reasons_quando_nothing_is_allowed() -> None:
    selection = select_templates(_MIXED, NucleiPermissions())

    assert dict(selection.excluded) == {
        "delete_not_allowed": 2,
        "unsafe": 1,
        "writes_not_allowed": 3,
    }


def test_orders_paths_deterministically_quando_manifest_is_shuffled() -> None:
    entries = [_entry(name) for name in ("c", "a", "b")]
    forward = select_templates(_manifest(*entries), NucleiPermissions())
    backward = select_templates(_manifest(*reversed(entries)), NucleiPermissions())

    assert forward == backward
    assert list(forward.paths) == sorted(forward.paths)


def test_treats_missing_methods_as_get_quando_login_is_on() -> None:
    selection = select_templates(_manifest(_entry(methods=[])), NucleiPermissions(login=True))

    assert len(selection.paths) == 1
    assert selection.excluded == ()
