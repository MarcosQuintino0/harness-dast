"""Trava por pilha (ADR 0035): formato do arquivo, decisão viva/órfã/ilegível e mensagens."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from harness_dast.domain.stack_lock import (
    LockHolder,
    LockVerdict,
    busy_message,
    describe_age,
    judge_lock,
    parse_lock,
    render_lock,
    unreadable_message,
)

START = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)


def holder(**changes: object) -> LockHolder:
    data: dict[str, object] = {
        "lock_id": "00000000000a",
        "command": "probe",
        "product": "demo",
        "pid": 321,
        "started_at": START,
    }
    data.update(changes)
    return LockHolder.model_validate(data)


def test_render_and_parse_round_trip_when_the_holder_is_valid() -> None:
    original = holder()

    assert parse_lock(render_lock(original)) == original


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n",
        "isto não é json",
        "[]",
        "{}",
        '{"lock_id": "00000000000a"}',
        json.dumps({**json.loads(render_lock(holder())), "extra": 1}),
        json.dumps({**json.loads(render_lock(holder())), "pid": 0}),
        json.dumps({**json.loads(render_lock(holder())), "pid": "abc"}),
        json.dumps({**json.loads(render_lock(holder())), "lock_id": "../x"}),
        json.dumps({**json.loads(render_lock(holder())), "started_at": "2026-11-14T10:00:00"}),
        json.dumps({**json.loads(render_lock(holder())), "started_at": "ontem"}),
        json.dumps({**json.loads(render_lock(holder())), "schema_version": 0}),
        render_lock(holder())[:40],
    ],
)
def test_parse_lock_returns_none_when_the_text_is_empty_corrupt_or_malformed(text: str) -> None:
    assert parse_lock(text) is None


def test_judge_lock_is_held_when_the_owner_is_alive() -> None:
    assert judge_lock(holder(), process_alive=True) is LockVerdict.HELD


def test_judge_lock_is_orphan_when_the_owner_is_dead() -> None:
    assert judge_lock(holder(), process_alive=False) is LockVerdict.ORPHAN


@pytest.mark.parametrize("alive", [True, False])
def test_judge_lock_is_unreadable_when_there_is_no_owner(alive: bool) -> None:
    assert judge_lock(None, process_alive=alive) is LockVerdict.UNREADABLE


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (timedelta(seconds=5), "há menos de 1 min"),
        (timedelta(minutes=5, seconds=30), "há 5 min"),
        (timedelta(hours=2, minutes=10), "há 2 h 10 min"),
        (timedelta(seconds=-30), "há menos de 1 min"),
    ],
)
def test_describe_age_uses_short_phrases(elapsed: timedelta, expected: str) -> None:
    assert describe_age(holder(), START + elapsed) == expected


def test_busy_message_says_who_holds_the_stack_and_what_to_do() -> None:
    message, hint = busy_message(holder(), START + timedelta(minutes=5), "/estado/stack.lock")

    assert "`probe`" in message
    assert "demo" in message
    assert "00000000000a" in message
    assert "321" in message
    assert "há 5 min" in message
    assert "hdast stop" in hint


def test_busy_message_tells_the_truth_about_stop_and_about_a_reused_pid() -> None:
    _, hint = busy_message(holder(), START, "/estado/stack.lock")

    assert "stop não solta a trava" in hint
    assert "stack down" in hint
    assert "reaproveitado o número de processo 321" in hint
    assert "apaga o arquivo /estado/stack.lock" in hint
    assert "O agente não apaga" in hint


def test_unreadable_message_points_to_the_file_and_to_stack_status() -> None:
    message, hint = unreadable_message("/estado/stack.lock")

    assert "/estado/stack.lock" in message
    assert "hdast stack status" in hint
