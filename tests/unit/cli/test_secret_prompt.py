"""Prompt de terminal do `hdast secret`: valor oculto com confirmação, remoção por nome digitado."""

import getpass
import io
import sys
from collections.abc import Callable

import pytest

from harness_dast.cli.commands.secret import TerminalSecretPrompt

VALUE = "valor-oculto-LITERAL-5k"


def feed(answers: list[str]) -> Callable[[str], str]:
    queue = iter(answers)

    def next_answer(_prompt: str = "") -> str:
        return next(queue)

    return next_answer


def test_read_value_asks_twice_hidden_and_returns_the_confirmed_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(getpass, "getpass", feed([VALUE, VALUE]))

    assert TerminalSecretPrompt().read_value("A") == VALUE
    assert VALUE not in capsys.readouterr().err


def test_read_value_asks_again_when_the_two_entries_differ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(getpass, "getpass", feed(["um", "dois", VALUE, VALUE]))

    assert TerminalSecretPrompt().read_value("A") == VALUE


def test_read_value_never_reads_the_visible_input(monkeypatch: pytest.MonkeyPatch) -> None:
    visible = io.StringIO("nao-deve-ser-lido\n")
    monkeypatch.setattr(sys, "stdin", visible)
    monkeypatch.setattr(getpass, "getpass", feed([VALUE, VALUE]))

    assert TerminalSecretPrompt().read_value("A") == VALUE
    assert visible.tell() == 0


@pytest.mark.parametrize(
    ("typed", "expected"), [("A", True), (" A ", True), ("a", False), ("", False)]
)
def test_confirm_removal_is_true_only_when_the_name_is_typed(
    monkeypatch: pytest.MonkeyPatch, typed: str, expected: bool
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(typed + "\n"))

    assert TerminalSecretPrompt().confirm_removal("A") is expected
