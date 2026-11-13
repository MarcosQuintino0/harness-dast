"""Orçamento de logins e conjunto de sessões."""

import pytest
from pydantic import ValidationError

from harness_dast.application.login_budget import LoginBudget, is_login_request
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.auth import LoginLimit
from harness_dast.domain.errors import PreflightError
from harness_dast.domain.http_messages import HttpRequest
from tests.fakes.runtime import ManualClock


def test_no_declared_limit_never_waits() -> None:
    clock = ManualClock()
    budget = LoginBudget(None, clock, clock)

    for _ in range(100):
        budget.acquire()

    assert clock.sleeps == []


def test_the_budget_waits_until_the_oldest_login_leaves_the_window() -> None:
    clock = ManualClock()
    budget = LoginBudget(LoginLimit(max_per_minute=2), clock, clock)

    budget.acquire()
    clock.advance(10)
    budget.acquire()
    budget.acquire()

    assert clock.sleeps == [pytest.approx(51.0)]


def test_logins_older_than_a_minute_do_not_count() -> None:
    clock = ManualClock()
    budget = LoginBudget(LoginLimit(max_per_minute=1), clock, clock)

    budget.acquire()
    clock.advance(62)
    budget.acquire()

    assert clock.sleeps == []


def test_a_limit_of_zero_is_not_a_valid_declaration() -> None:
    with pytest.raises(ValidationError):
        LoginLimit(max_per_minute=0)


def request(method: str, url: str) -> HttpRequest:
    return HttpRequest(method=method, url=url, operation_id="x", route="auth")


def test_only_a_post_to_the_login_path_is_a_login() -> None:
    login = "/api/auth/login"

    assert is_login_request(request("POST", "http://h/api/auth/login"), login)
    assert is_login_request(request("POST", "http://h/api/auth/login/?a=1"), login)
    assert not is_login_request(request("GET", "http://h/api/auth/login"), login)
    assert not is_login_request(request("POST", "http://h/api/outro"), login)
    assert not is_login_request(request("POST", "http://h/api/auth/login"), None)


class _Session:
    def __init__(self, fail: bool) -> None:
        self.opened = 0
        self._fail = fail

    def open(self) -> None:
        self.opened += 1
        if self._fail:
            raise PreflightError("login recusado", hint="confira")


def test_the_pool_opens_each_account_once() -> None:
    made: dict[str, _Session] = {}

    def make(alias: str) -> _Session:
        return made.setdefault(alias, _Session(fail=False))

    pool = SessionPool(make)  # type: ignore[arg-type]  # dublê estrutural de AccountSession

    assert pool.get("a") is pool.get("a")
    assert made["a"].opened == 1


def test_a_failed_account_is_not_retried_because_each_retry_spends_a_login() -> None:
    made: list[_Session] = []

    def make(alias: str) -> _Session:
        made.append(_Session(fail=True))
        return made[-1]

    pool = SessionPool(make)  # type: ignore[arg-type]  # dublê estrutural de AccountSession

    for _ in range(3):
        with pytest.raises(PreflightError):
            pool.get("a")

    assert len(made) == 1
    assert made[0].opened == 1
