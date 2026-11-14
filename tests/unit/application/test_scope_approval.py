"""Casos de uso da aprovação humana do escopo e o repositório conferido (ADR 0037)."""

import copy
from typing import Any

import pytest

from harness_dast.application.scope_approval import ApprovedProfileRepository, ScopeApprovals
from harness_dast.domain.errors import ConfigError, ScopeNotApproved
from harness_dast.domain.profile import ProductProfile
from tests.fakes.approvals import (
    APPROVED_AT,
    InMemoryApprovalStore,
    ScriptedApprovalPrompt,
    approve_profile,
)
from tests.fakes.clock import FixedClock
from tests.fakes.profile_data import valid_profile, valid_profile_data
from tests.fakes.profile_repository import InMemoryProfileRepository


class Rig:
    def __init__(self, *, answer: bool = True) -> None:
        self.profiles = InMemoryProfileRepository()
        self.profiles.add(valid_profile(), existing_files={"./openapi.json"})
        self.store = InMemoryApprovalStore()
        self.prompt = ScriptedApprovalPrompt(answer)
        self.guarded = ApprovedProfileRepository(self.profiles, self.store)
        self.use_case = ScopeApprovals(
            self.profiles, self.store, self.prompt, FixedClock(APPROVED_AT)
        )

    def edit_profile(self, mutation: Any) -> None:
        data = copy.deepcopy(valid_profile_data())
        mutation(data)
        self.profiles.add(ProductProfile.from_data(data), existing_files={"./openapi.json"})


# ---------------------------------------------------------- repositório conferido


def test_guarded_load_refuses_a_profile_never_approved() -> None:
    rig = Rig()

    with pytest.raises(ScopeNotApproved) as caught:
        rig.guarded.load("demo")

    assert caught.value.state == "not_approved"


def test_guarded_load_returns_the_profile_once_a_person_approved_it() -> None:
    rig = Rig()
    approve_profile(rig.store, valid_profile())

    assert rig.guarded.load("demo") == valid_profile()


def test_guarded_load_refuses_when_the_profile_changed_and_names_the_block() -> None:
    rig = Rig()
    approve_profile(rig.store, valid_profile())
    rig.edit_profile(lambda d: d["scope"]["allow"][0]["paths"].append("/novo/**"))

    with pytest.raises(ScopeNotApproved) as caught:
        rig.guarded.load("demo")

    assert caught.value.state == "changed"
    assert caught.value.changed_blocks == ("scope.allow",)
    assert "scope.allow" in caught.value.message


def test_guarded_load_accepts_a_change_outside_the_protection() -> None:
    rig = Rig()
    approve_profile(rig.store, valid_profile())
    rig.edit_profile(lambda d: d.update(probe={"health_path": "/api/saude"}))

    assert rig.guarded.load("demo").probe.health_path == "/api/saude"


def test_guarded_load_treats_an_unreadable_approval_as_invalid() -> None:
    rig = Rig()
    rig.store.invalid.add("demo")

    with pytest.raises(ScopeNotApproved) as caught:
        rig.guarded.load("demo")

    assert caught.value.state == "invalid"


def test_guarded_load_reports_a_missing_profile_before_the_approval() -> None:
    rig = Rig()

    with pytest.raises(ConfigError):
        rig.guarded.load("nao-existe")


def test_guarded_repository_still_lists_missing_files() -> None:
    rig = Rig()

    assert rig.guarded.missing_files("demo", valid_profile()) == ()


# ---------------------------------------------------------- aprovar


def test_approve_without_a_terminal_is_refused_and_writes_nothing() -> None:
    rig = Rig()

    with pytest.raises(ConfigError) as caught:
        rig.use_case.approve("demo", interactive=False)

    assert "Só uma pessoa" in caught.value.message
    assert rig.store.items == {}
    assert rig.prompt.shown == []


def test_approve_shows_the_summary_and_writes_when_the_person_confirms() -> None:
    rig = Rig()

    report = rig.use_case.approve("demo", interactive=True)

    assert report.approved is True
    assert report.already_approved is False
    assert report.approved_at == APPROVED_AT.isoformat()
    product, summary, changes = rig.prompt.shown[0]
    assert product == "demo"
    assert any("Pode alcançar" in line for line in summary)
    assert changes == ()
    assert rig.guarded.load("demo") == valid_profile()


def test_wrong_confirmation_does_not_approve_and_writes_nothing() -> None:
    rig = Rig(answer=False)

    report = rig.use_case.approve("demo", interactive=True)

    assert report.approved is False
    assert report.approved_at is None
    assert rig.store.items == {}
    with pytest.raises(ScopeNotApproved):
        rig.guarded.load("demo")


def test_approving_again_without_changes_asks_nothing_and_keeps_the_first_instant() -> None:
    rig = Rig()
    first = rig.use_case.approve("demo", interactive=True)
    rig.prompt.shown.clear()

    again = rig.use_case.approve("demo", interactive=True)

    assert again.already_approved is True
    assert again.approved_at == first.approved_at
    assert rig.prompt.shown == []


def test_reapproving_after_a_change_shows_what_changed_and_accepts_the_new_profile() -> None:
    rig = Rig()
    rig.use_case.approve("demo", interactive=True)
    rig.edit_profile(lambda d: d["limits"].update(requests_per_second=9))
    rig.prompt.shown.clear()

    report = rig.use_case.approve("demo", interactive=True)

    assert report.approved is True
    assert report.changed_blocks == ("limits",)
    assert rig.prompt.shown[0][2] == ("limits: limites de carga",)
    assert rig.guarded.load("demo").limits.requests_per_second == 9


def test_declining_a_new_approval_keeps_the_profile_blocked() -> None:
    rig = Rig()
    rig.use_case.approve("demo", interactive=True)
    rig.edit_profile(lambda d: d["scope"].update(deny_paths=[]))
    rig.prompt.answer = False

    report = rig.use_case.approve("demo", interactive=True)

    assert report.approved is False
    with pytest.raises(ScopeNotApproved):
        rig.guarded.load("demo")


def test_approve_replaces_an_invalid_record() -> None:
    rig = Rig()
    rig.store.invalid.add("demo")

    report = rig.use_case.approve("demo", interactive=True)

    assert report.approved is True
    assert rig.guarded.load("demo") == valid_profile()


def test_a_write_failure_is_reported_and_leaves_the_profile_blocked() -> None:
    rig = Rig()
    rig.store.fail_writes = True

    with pytest.raises(ConfigError):
        rig.use_case.approve("demo", interactive=True)

    with pytest.raises(ScopeNotApproved):
        rig.guarded.load("demo")


def test_approve_of_an_unknown_product_is_a_config_error() -> None:
    rig = Rig()

    with pytest.raises(ConfigError):
        rig.use_case.approve("nao-existe", interactive=True)


# ---------------------------------------------------------- consultar


def test_status_walks_through_not_approved_approved_and_changed() -> None:
    rig = Rig()
    assert rig.use_case.status("demo").state == "not_approved"

    rig.use_case.approve("demo", interactive=True)
    assert rig.use_case.status("demo").state == "approved"

    rig.edit_profile(lambda d: d["auth"]["accounts"][0].update(role="admin"))
    info = rig.use_case.status("demo")
    assert info.state == "changed"
    assert info.changed_blocks == ("auth",)
    assert "auth" in info.message


def test_status_of_an_invalid_record_does_not_raise() -> None:
    rig = Rig()
    rig.store.invalid.add("demo")

    info = rig.use_case.status("demo")

    assert info.state == "invalid"
    assert info.approved_at is None
