"""Aprovação humana: estados, recusa de registro adulterado e mensagens (ADR 0037)."""

import copy
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError, ExitCode, ScopeNotApproved, ScopeViolation
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_approval import (
    ScopeApproval,
    check_approval,
    create_approval,
)
from harness_dast.domain.scope_approval_summary import describe_protection
from tests.fakes.approvals import APPROVED_AT, approval_for
from tests.fakes.profile_data import valid_profile, valid_profile_data


def profile_with(mutation: Any) -> ProductProfile:
    data = copy.deepcopy(valid_profile_data())
    mutation(data)
    return ProductProfile.from_data(data)


def tampered(approval: ScopeApproval, **changes: Any) -> dict[str, Any]:
    return {**approval.model_dump(mode="json"), **changes}


def test_profile_without_a_record_is_not_approved() -> None:
    check = check_approval(valid_profile(), None)

    assert check.state == "not_approved"
    assert check.approved_at is None


def test_untouched_profile_is_approved() -> None:
    profile = valid_profile()

    check = check_approval(profile, approval_for(profile))

    assert check.state == "approved"
    assert check.approved_at == APPROVED_AT.isoformat()
    check.ensure_approved()


def test_changed_profile_reports_only_the_blocks_that_changed_in_display_order() -> None:
    approval = approval_for(valid_profile())
    changed = profile_with(
        lambda d: (d["limits"].update(requests_per_second=9), d["scope"].update(deny_paths=[]))
    )

    check = check_approval(changed, approval)

    assert check.state == "changed"
    assert check.changed_blocks == ("scope.deny_paths", "limits")


def test_ensure_approved_raises_with_code_exit_three_and_names_the_changed_block() -> None:
    approval = approval_for(valid_profile())
    changed = profile_with(lambda d: d["scope"]["allow"][0]["methods"].append("DELETE"))

    with pytest.raises(ScopeNotApproved) as caught:
        check_approval(changed, approval).ensure_approved()

    error = caught.value
    assert error.code == "SCOPE_NOT_APPROVED"
    assert error.exit_code == ExitCode.SCOPE
    assert error.state == "changed"
    assert error.changed_blocks == ("scope.allow",)
    assert "scope.allow" in error.message
    assert "hdast profile approve demo" in (error.hint or "")
    assert "agente" in (error.hint or "")


def test_ensure_approved_raises_for_a_profile_never_approved() -> None:
    with pytest.raises(ScopeNotApproved) as caught:
        check_approval(valid_profile(), None).ensure_approved()

    assert caught.value.state == "not_approved"
    assert "ainda não foi aprovado" in caught.value.message


def test_record_of_another_product_is_invalid_for_this_profile() -> None:
    other = approval_for(valid_profile("outro"))

    check = check_approval(valid_profile("demo"), other)

    assert check.state == "invalid"
    with pytest.raises(ScopeNotApproved):
        check.ensure_approved()


def test_scope_not_approved_is_not_a_scope_violation_so_nothing_swallows_it() -> None:
    assert not issubclass(ScopeNotApproved, ScopeViolation)


def test_record_with_a_digest_that_does_not_match_its_blocks_is_refused() -> None:
    approval = approval_for(valid_profile())

    with pytest.raises(ValidationError):
        ScopeApproval.model_validate(tampered(approval, digest="a" * 64))


def test_record_with_one_edited_block_digest_is_refused() -> None:
    approval = approval_for(valid_profile())
    blocks = dict(approval.blocks)
    blocks["limits"] = "b" * 64

    with pytest.raises(ValidationError):
        ScopeApproval.model_validate(tampered(approval, blocks=blocks))


@pytest.mark.parametrize("bad", ["", "xyz", "A" * 64, "a" * 63, "g" * 64])
def test_record_with_a_malformed_digest_is_refused(bad: str) -> None:
    approval = approval_for(valid_profile())

    with pytest.raises(ValidationError):
        ScopeApproval.model_validate(tampered(approval, digest=bad))


@pytest.mark.parametrize("version", [0, 1, 3, "2", None])
def test_record_with_an_unknown_schema_version_is_refused(version: object) -> None:
    approval = approval_for(valid_profile())

    with pytest.raises(ValidationError):
        ScopeApproval.model_validate(tampered(approval, schema_version=version))


def test_record_with_an_unknown_field_is_refused() -> None:
    approval = approval_for(valid_profile())

    with pytest.raises(ValidationError):
        ScopeApproval.model_validate(tampered(approval, extra="x"))


def test_record_with_a_product_that_is_not_a_slug_is_refused() -> None:
    approval = approval_for(valid_profile())

    with pytest.raises(ValidationError):
        ScopeApproval.model_validate(tampered(approval, product="../x"))


def test_record_with_a_control_character_in_the_summary_is_refused() -> None:
    approval = approval_for(valid_profile())

    with pytest.raises(ValidationError):
        ScopeApproval.model_validate(tampered(approval, summary=["linha\x00ruim"]))


def test_create_approval_refuses_an_instant_without_timezone() -> None:
    with pytest.raises(ConfigError):
        create_approval(valid_profile(), datetime(2026, 11, 14, 12, 0), ())


def test_create_approval_is_deterministic_for_the_same_profile_and_instant() -> None:
    profile = valid_profile()

    first = create_approval(
        profile, datetime(2026, 11, 14, tzinfo=UTC), describe_protection(profile)
    )
    second = create_approval(
        profile, datetime(2026, 11, 14, tzinfo=UTC), describe_protection(profile)
    )

    assert first == second


def test_summary_shows_every_protection_the_person_approves_and_no_secret_value() -> None:
    profile = profile_with(
        lambda d: (
            d["scope"].update(path_mode="wide"),
            d.update(scan={"strength": "MEDIUM", "mutating_methods": ["PUT"]}),
        )
    )

    text = "\n".join(describe_protection(profile))

    assert "https://api.hml.acme-teste.net.br" in text
    assert "/api/**" in text
    assert "GET, POST" in text
    assert "/api/admin/**" in text
    assert "AMPLO" in text
    assert "CHG-4821" in text
    assert "2999-12-31" in text
    assert "seg,ter,qua,qui,sex,sab,dom 00:00-24:00 UTC" in text
    assert "5.0 req/s, 60 min, 2 thread(s)" in text
    assert "user_a (papel: usuario)" in text
    assert "env:ACME_USER_A_SENHA" in text
    assert "força MEDIUM" in text
    assert "PUT" in text
    assert "POST /api/auth/login" in text


def test_summary_of_a_strict_profile_says_strict_and_names_no_denied_path_when_none() -> None:
    profile = profile_with(lambda d: d["scope"].update(deny_paths=[]))

    text = "\n".join(describe_protection(profile))

    assert "estrito" in text
    assert "nenhum caminho negado" in text


def test_summary_shows_scan_policy_authz_and_cleanup_the_person_approves() -> None:
    profile = profile_with(
        lambda d: d.update(
            scan={"fail_on": "high", "disable_rules": [40018], "max_scan_minutes": 30},
            authz={"public_operations": ["listar"], "disabled_checks": ["vertical"]},
            cleanup={
                "type": "oracle_sql",
                "script": "./cleanup/cleanup.sql",
                "connection": {"secret_ref": "env:ACME_ORACLE"},
                "requires_confirmation": True,
                "allowed_tables": ["PEDIDOS"],
                "max_rows": 50,
            },
        )
    )

    text = "\n".join(describe_protection(profile))

    assert "regras do ZAP desligadas: 40018" in text
    assert "30 min por varredura" in text
    assert "a partir de: high" in text
    assert "listar" in text
    assert "verificações desligadas: vertical" in text
    assert "script ./cleanup/cleanup.sql" in text
    assert "env:ACME_ORACLE" in text
    assert "tabelas permitidas: PEDIDOS; até 50 linhas" in text


def test_summary_without_cleanup_says_it_is_not_configured() -> None:
    text = "\n".join(describe_protection(valid_profile()))

    assert "Limpeza do ambiente: não configurada." in text


def test_an_approval_of_the_old_calculation_version_is_refused_when_read() -> None:
    old = tampered(approval_for(valid_profile()), schema_version=1)

    with pytest.raises(ValidationError):
        ScopeApproval.model_validate(old)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("scan", {"fail_on": "none", "disable_rules": [40018]}),
        ("authz", {"public_operations": ["listar"]}),
    ],
)
def test_agent_edit_after_approval_to_scan_or_authz_makes_it_changed(
    key: str, value: dict[str, Any]
) -> None:
    approval = approval_for(valid_profile())
    edited = profile_with(lambda d: d.update({key: value}))

    check = check_approval(edited, approval)

    assert check.state == "changed"
    assert check.changed_blocks == (key,)


def test_changed_message_names_each_block_in_plain_language_without_nested_parentheses() -> None:
    approval = approval_for(valid_profile())
    changed = profile_with(
        lambda d: (
            d["scope"]["allow"][0]["methods"].append("DELETE"),
            d["limits"].update(requests_per_second=9),
        )
    )

    message = check_approval(changed, approval).message()

    assert "o que pode ser alcançado (scope.allow)" in message
    assert "limites de carga (limits)" in message
    assert "((" not in message
    assert message.count("(") == message.count(")")


def test_summary_shows_the_authorized_writes_only_when_they_are_on() -> None:
    off_profile = profile_with(lambda d: d.update(authz={}))
    on_profile = profile_with(lambda d: d.update(authz={"allow_writes": True}))
    off = " | ".join(describe_protection(off_profile))
    on = " | ".join(describe_protection(on_profile))

    assert "ESCRITA AUTORIZADA" not in off
    assert "ESCRITA AUTORIZADA (authz.allow_writes: true)" in on


def test_turning_allow_writes_on_after_approval_makes_it_changed_and_off_keeps_it_approved() -> (
    None
):
    approval = approval_for(valid_profile())

    still = check_approval(
        profile_with(lambda d: d.update(authz={"allow_writes": False})), approval
    )
    changed = check_approval(
        profile_with(lambda d: d.update(authz={"allow_writes": True})), approval
    )

    assert still.state == "approved"
    assert changed.state == "changed"
    assert "authz" in changed.changed_blocks
