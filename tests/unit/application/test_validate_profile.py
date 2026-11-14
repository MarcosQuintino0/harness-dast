import json
from datetime import datetime
from typing import Any

import pytest

from harness_dast.application.validate_profile import ProfileReport, ValidateProfile
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from tests.fakes.approvals import InMemoryApprovalStore, approval_for
from tests.fakes.clock import FixedClock, utc
from tests.fakes.profile_data import valid_profile, valid_profile_data
from tests.fakes.profile_repository import InMemoryProfileRepository

# Terça-feira 2026-11-10, meio-dia em UTC.
NOON = utc(2026, 11, 10, 12)


def _validate(
    profile: ProductProfile,
    *,
    now: datetime = NOON,
    existing_files: set[str] | None = None,
) -> ProfileReport:
    repository = InMemoryProfileRepository()
    repository.add(
        profile, existing_files={"./openapi.json"} if existing_files is None else existing_files
    )
    return ValidateProfile(repository, FixedClock(now), InMemoryApprovalStore()).execute(
        profile.product
    )


def _profile(mutate: Any = None, *, with_cleanup: bool = False) -> ProductProfile:
    data = valid_profile_data(with_cleanup=with_cleanup)
    if mutate is not None:
        mutate(data)
    return ProductProfile.from_data(data)


def _codes(report: ProfileReport) -> list[str]:
    return [issue.code for issue in report.issues]


def test_report_is_runnable_when_profile_is_complete_and_window_is_open() -> None:
    report = _validate(valid_profile())

    assert report.runnable is True
    assert report.issues == ()
    assert report.authorization_valid_now is True
    assert report.window_open_now is True


def test_report_summarizes_profile_data_when_profile_is_valid() -> None:
    report = _validate(
        valid_profile(with_cleanup=True), existing_files={"./openapi.json", "./cleanup/cleanup.sql"}
    )

    assert report.product == "demo"
    assert report.environment_name == "homolog"
    assert report.base_url_host == "api.hml.acme-teste.net.br"
    assert report.allow_rules == 1
    assert report.deny_paths == ("/api/admin/**",)
    assert report.auth_type == "login_password"
    assert [(a.alias, a.role) for a in report.accounts] == [("user_a", "usuario")]
    assert report.authorization_reference == "CHG-4821"
    assert report.authorization_valid_until == "2999-12-31"
    assert report.limits.requests_per_second == 5
    assert report.limits.max_duration_minutes == 60
    assert report.limits.zap_threads_per_host == 2
    assert report.cleanup_configured is True
    assert report.checked_at == NOON.isoformat()
    assert report.runnable is True


def test_window_summary_is_readable_when_window_crosses_midnight() -> None:
    profile = _profile(
        lambda d: d["scope"].update(windows=["seg-sex 20:00-06:00 America/Sao_Paulo"])
    )

    window = _validate(profile).windows[0]

    assert window.days == ("seg", "ter", "qua", "qui", "sex")
    assert (window.start, window.end, window.timezone) == ("20:00", "06:00", "America/Sao_Paulo")


def test_window_end_is_24_00_when_window_covers_the_whole_day() -> None:
    assert _validate(valid_profile()).windows[0].end == "24:00"


def test_report_is_not_runnable_when_window_is_closed() -> None:
    profile = _profile(lambda d: d["scope"].update(windows=["seg-sex 20:00-22:00 UTC"]))

    report = _validate(profile)

    assert report.window_open_now is False
    assert report.windows[0].open_now is False
    assert _codes(report) == ["WINDOW_CLOSED"]
    assert report.runnable is False


def test_window_is_open_when_any_of_several_windows_is_open() -> None:
    profile = _profile(
        lambda d: d["scope"].update(windows=["seg-sex 20:00-22:00 UTC", "ter 11:00-13:00 UTC"])
    )

    report = _validate(profile)

    assert [w.open_now for w in report.windows] == [False, True]
    assert report.window_open_now is True


def test_report_is_not_runnable_when_authorization_expired() -> None:
    profile = _profile(lambda d: d["scope"]["authorization"].update(valid_until="2026-11-09"))

    report = _validate(profile)

    assert report.authorization_valid_now is False
    assert _codes(report) == ["AUTHORIZATION_EXPIRED"]
    assert "CHG-4821" in report.issues[0].message


def test_report_lists_each_missing_file_when_files_do_not_exist() -> None:
    profile = valid_profile(with_cleanup=True)

    report = _validate(profile, existing_files=set())

    fields = {i.field for i in report.issues if i.code == "FILE_MISSING"}
    assert fields == {"openapi", "cleanup.script"}
    assert report.runnable is False


def test_report_flags_placeholders_when_profile_comes_from_the_template() -> None:
    def to_template(data: dict[str, Any]) -> None:
        data["environment"]["base_url"] = "https://meu-produto.hml.exemplo.com.br"
        data["scope"]["allow"][0]["host"] = "meu-produto.hml.exemplo.com.br"
        data["scope"]["authorization"]["reference"] = "SEC-0000"
        account = data["auth"]["accounts"][0]
        account["username"] = {"secret_ref": "env:MEU_PRODUTO_USER_A_LOGIN"}

    report = _validate(_profile(to_template))

    assert _codes(report) == [
        "PLACEHOLDER_HOST",
        "PLACEHOLDER_HOST",
        "PLACEHOLDER_AUTHORIZATION",
        "PLACEHOLDER_SECRET_REF",
    ]
    assert report.issues[3].field == "auth.accounts[user_a].username"


def test_report_flags_cleanup_connection_when_it_keeps_the_example_name() -> None:
    def keep_example(data: dict[str, Any]) -> None:
        data["cleanup"]["connection"] = {"secret_ref": "env:MEU_PRODUTO_ORACLE_LIMPEZA"}

    profile = _profile(keep_example, with_cleanup=True)

    report = _validate(profile, existing_files={"./openapi.json", "./cleanup/cleanup.sql"})

    assert [i.field for i in report.issues] == ["cleanup.connection"]


def test_report_never_contains_secret_references_or_their_names() -> None:
    profile = valid_profile(with_cleanup=True)

    dumped = json.dumps(_validate(profile, existing_files=set()).model_dump(mode="json"))

    for forbidden in ("ACME_USER_A", "ACME_ORACLE", "secret_ref", "env:"):
        assert forbidden not in dumped


def test_validation_raises_config_error_when_profile_does_not_exist() -> None:
    use_case = ValidateProfile(
        InMemoryProfileRepository(), FixedClock(NOON), InMemoryApprovalStore()
    )

    with pytest.raises(ConfigError):
        use_case.execute("inexistente")


def test_validation_raises_config_error_when_clock_has_no_timezone() -> None:
    repository = InMemoryProfileRepository()
    repository.add(valid_profile(), existing_files={"./openapi.json"})
    naive = FixedClock(datetime(2026, 11, 10, 12))

    with pytest.raises(ConfigError):
        ValidateProfile(repository, naive, InMemoryApprovalStore()).execute("demo")


def test_report_is_a_fresh_snapshot_when_the_clock_moves() -> None:
    repository = InMemoryProfileRepository()
    profile = _profile(lambda d: d["scope"].update(windows=["ter 11:00-13:00 UTC"]))
    repository.add(profile, existing_files={"./openapi.json"})
    clock = FixedClock(NOON)
    use_case = ValidateProfile(repository, clock, InMemoryApprovalStore())

    open_report = use_case.execute("demo")
    clock.advance_to(utc(2026, 11, 10, 14))
    closed_report = use_case.execute("demo")

    assert (open_report.window_open_now, closed_report.window_open_now) == (True, False)


def test_report_carries_the_approval_state_without_touching_runnable() -> None:
    repository = InMemoryProfileRepository()
    profile = valid_profile()
    repository.add(profile, existing_files={"./openapi.json"})
    store = InMemoryApprovalStore()
    use_case = ValidateProfile(repository, FixedClock(NOON), store)

    before = use_case.execute("demo")
    store.write(approval_for(profile))
    after = use_case.execute("demo")

    assert (before.approval.state, after.approval.state) == ("not_approved", "approved")
    assert before.runnable is True
    assert after.runnable is True
    assert after.approval.approved_at is not None
