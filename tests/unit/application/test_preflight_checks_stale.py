"""`STACK_STALE` não vira verificação reprovada: sobe até a CLI (ADR 0081)."""

import pytest

from harness_dast.application.preflight_checks import failure_check, run_step
from harness_dast.domain.errors import ConfigError, StackStale


def test_failure_check_repassa_stack_stale_em_vez_de_reprovar_a_verificacao() -> None:
    with pytest.raises(StackStale):
        failure_check("login:user_a", StackStale("pilha velha", hint="recrie"))


def test_run_step_repassa_stack_stale_do_login() -> None:
    def login() -> None:
        raise StackStale("pilha velha", hint="recrie")

    with pytest.raises(StackStale):
        run_step("login:user_a", login, "ok")


def test_run_step_continua_reprovando_outros_erros_do_harness() -> None:
    def login() -> None:
        raise ConfigError("falhou", hint="tente")

    check = run_step("login:user_a", login, "ok")

    assert check.ok is False
    assert "falhou" in check.detail
