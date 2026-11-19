"""Compatibilidade da aprovação e exibição da declaração do Nuclei."""

from datetime import UTC, datetime

import pytest

from harness_dast.domain import nuclei_version
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_approval import check_approval, create_approval
from harness_dast.domain.scope_approval_summary import describe_protection
from harness_dast.domain.scope_fingerprint import block_digests, combine_digests
from harness_dast.domain.setup_notes import approval_notes
from tests.fakes.profile_data import valid_profile_data

APPROVED_AT = datetime(2026, 11, 19, tzinfo=UTC)
# SHA-256 calculados na branch antes de adicionar os três campos do ADR 0122.
LEGACY_DIGESTS = (
    ((), "c279ffb213a1eeaeca1c2ee3231a4a2e1d50da4df12b020b79edb8e79f4f3965"),
    (("inventory",), "da69e542d62bac64dfb5137ff8b9861b4785f0cf5a727607ac5c889393f28f6c"),
    (("experimental_rules",), "3a7de8751db30b316cc68433f03288e0c7b95f0155b223567fc662bd704f4fcd"),
    (
        ("experimental_rules", "inventory"),
        "c7a234b783f10cc5896b54c70dcbf2fccd36139152574a49f00e04b149d528cb",
    ),
    (("allow_rate_tests",), "5e8da05a1eea62305c950582e127e82c7ffbb863deeb565709223c1853c2965c"),
    (
        ("allow_rate_tests", "inventory"),
        "ee3bd884a589c37d251d54a1aaaf28df8442bd92a5466d744df4ccd63e85287d",
    ),
    (
        ("allow_rate_tests", "experimental_rules"),
        "7e9d896dbd4272a308d293a2b3d0276359f5cc79523a6e1f73955f3b100f6bcb",
    ),
    (
        ("allow_rate_tests", "experimental_rules", "inventory"),
        "74680c2d753b4c77f42cdd3dcce60059b982649251ef941bd7c8564c2f7027ab",
    ),
)


def _profile(**checks: bool) -> ProductProfile:
    data = valid_profile_data()
    data["extra_checks"] = checks
    return ProductProfile.from_data(data)


@pytest.mark.parametrize(("enabled", "expected"), LEGACY_DIGESTS)
def test_fingerprint_matches_the_original_when_nuclei_is_off(
    enabled: tuple[str, ...], expected: str
) -> None:
    legacy = {name: True for name in enabled}
    profile = _profile(**legacy)
    explicitly_disabled = _profile(
        **legacy, nuclei=False, nuclei_login=False, nuclei_wide_paths=False
    )

    assert combine_digests(profile.product, block_digests(profile)) == expected
    assert combine_digests(profile.product, block_digests(explicitly_disabled)) == expected


@pytest.mark.parametrize("field", ["nuclei", "nuclei_login", "nuclei_wide_paths"])
def test_approval_becomes_stale_when_any_nuclei_flag_changes(field: str) -> None:
    before = _profile(inventory=True)
    after = _profile(inventory=True, **{field: True})
    approval = create_approval(before, APPROVED_AT, ())

    assert check_approval(after, approval).changed_blocks == ("extra_checks",)


@pytest.mark.parametrize(
    "field", ["NUCLEI_VERSION", "TEMPLATES_VERSION", "TEMPLATES_ARCHIVE_SHA256"]
)
@pytest.mark.parametrize("enabled", [False, True])
def test_catalog_and_engine_versions_only_bind_approval_when_nuclei_is_on(
    monkeypatch: pytest.MonkeyPatch, field: str, enabled: bool
) -> None:
    profile = _profile(nuclei=enabled, inventory=True)
    approval = create_approval(profile, APPROVED_AT, ())

    monkeypatch.setattr(nuclei_version, field, "0" * 64)

    assert check_approval(profile, approval).state == ("changed" if enabled else "approved")


@pytest.mark.parametrize(("login", "login_word"), [(False, "não"), (True, "sim")])
@pytest.mark.parametrize(("wide", "wide_word"), [(False, "não"), (True, "sim")])
def test_both_approval_summaries_describe_the_declared_nuclei_options(
    login: bool, login_word: str, wide: bool, wide_word: str
) -> None:
    profile = _profile(nuclei=True, nuclei_login=login, nuclei_wide_paths=wide)
    expected = (
        f"Nuclei: verificações conhecidas da comunidade, versão "
        f"{nuclei_version.TEMPLATES_VERSION} dos modelos. "
        f"Com login: {login_word}. Endereços fora do Swagger: {wide_word}. "
        "Escrita: não. Apagar: não."
    )

    for summary in (approval_notes(profile, ()), describe_protection(profile)):
        assert expected in summary
        assert (
            "O Nuclei pode consultar qualquer caminho das origens aprovadas, mesmo fora do "
            "Swagger. Os caminhos negados continuam negados." in summary
        ) is wide


@pytest.mark.parametrize("field", ["nuclei_login", "nuclei_wide_paths"])
def test_both_approval_summaries_warn_when_only_a_secondary_option_is_on(field: str) -> None:
    profile = _profile(**{field: True})

    for summary in (approval_notes(profile, ()), describe_protection(profile)):
        (line,) = (line for line in summary if line.startswith("Nuclei:"))
        assert "ficam sem efeito" in line


def test_both_approval_summaries_omit_nuclei_when_all_flags_are_off() -> None:
    profile = _profile()

    assert all(
        "Nuclei:" not in line
        for line in (*approval_notes(profile, ()), *describe_protection(profile))
    )


def _writing_profile(*, delete: bool) -> ProductProfile:
    data = valid_profile_data()
    data["extra_checks"] = {"nuclei": True}
    data["authz"] = {"allow_writes": True}
    data["negative"] = {"allow_writes": True}
    data["scan"] = {"allow_upload_scan": True}
    if delete:
        data["scope"]["allow"][0]["methods"] = ["GET", "POST", "DELETE"]
    return ProductProfile.from_data(data)


@pytest.mark.parametrize(("delete", "delete_word"), [(False, "não"), (True, "sim")])
def test_both_approval_summaries_show_write_and_delete_when_the_three_writes_are_on(
    delete: bool, delete_word: str
) -> None:
    profile = _writing_profile(delete=delete)

    for summary in (approval_notes(profile, ()), describe_protection(profile)):
        assert any(
            line.endswith(f"Escrita: sim. Apagar: {delete_word}.")
            for line in summary
            if line.startswith("Nuclei:")
        )
