"""`FileStackLock`: criação exclusiva e completa, leitura de lixo e apagar sob guarda."""

import os
import threading
from datetime import timedelta
from pathlib import Path

import pytest

from harness_dast.adapters.storage.stack_lock import (
    GUARD_FILE_NAME,
    GUARD_STALE_SECONDS,
    LOCK_FILE_NAME,
    FileStackLock,
)
from harness_dast.domain.errors import ConfigError
from tests.fakes.clock import FixedClock, utc


def make(tmp_path: Path) -> tuple[FileStackLock, FixedClock]:
    clock = FixedClock(utc(2026, 11, 14, 10, 0))
    return FileStackLock(tmp_path / "estado", clock), clock


def test_create_exclusive_writes_the_whole_content_and_creates_the_state_folder(
    tmp_path: Path,
) -> None:
    lock, _ = make(tmp_path)

    created = lock.create_exclusive("conteúdo completo\n")

    assert created is True
    assert lock.location() == tmp_path / "estado" / LOCK_FILE_NAME
    assert lock.read() == "conteúdo completo\n"


def test_create_exclusive_returns_false_and_keeps_the_first_content_when_it_exists(
    tmp_path: Path,
) -> None:
    lock, _ = make(tmp_path)
    lock.create_exclusive("primeiro")

    assert lock.create_exclusive("segundo") is False

    assert lock.read() == "primeiro"


def test_create_exclusive_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    lock, _ = make(tmp_path)
    lock.create_exclusive("a")
    lock.create_exclusive("b")

    assert sorted(item.name for item in (tmp_path / "estado").iterdir()) == [LOCK_FILE_NAME]


def test_only_one_of_many_concurrent_creators_wins(tmp_path: Path) -> None:
    lock, _ = make(tmp_path)
    results: list[bool] = []
    barrier = threading.Barrier(8)

    def contender(number: int) -> None:
        barrier.wait()
        results.append(lock.create_exclusive(f"dono {number}"))

    threads = [threading.Thread(target=contender, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == 1
    assert lock.read() in {f"dono {n}" for n in range(8)}


def test_read_is_none_when_there_is_no_lock(tmp_path: Path) -> None:
    lock, _ = make(tmp_path)

    assert lock.read() is None


def test_read_returns_text_for_an_empty_file(tmp_path: Path) -> None:
    lock, _ = make(tmp_path)
    (tmp_path / "estado").mkdir()
    lock.location().write_bytes(b"")

    assert lock.read() == ""


def test_read_does_not_fail_on_invalid_utf8_bytes(tmp_path: Path) -> None:
    lock, _ = make(tmp_path)
    (tmp_path / "estado").mkdir()
    lock.location().write_bytes(b"\xff\xfe\x00lixo")

    text = lock.read()

    assert text is not None
    assert "lixo" in text


def test_remove_if_unchanged_deletes_the_lock_when_the_content_matches(tmp_path: Path) -> None:
    lock, _ = make(tmp_path)
    lock.create_exclusive("meu")

    assert lock.remove_if_unchanged("meu") is True

    assert lock.read() is None
    assert not (tmp_path / "estado" / GUARD_FILE_NAME).exists()


def test_remove_if_unchanged_keeps_a_lock_whose_content_changed(tmp_path: Path) -> None:
    lock, _ = make(tmp_path)
    lock.create_exclusive("de outra execução")

    assert lock.remove_if_unchanged("meu") is False

    assert lock.read() == "de outra execução"
    assert not (tmp_path / "estado" / GUARD_FILE_NAME).exists()


def test_remove_if_unchanged_is_false_when_there_is_no_lock(tmp_path: Path) -> None:
    lock, _ = make(tmp_path)
    (tmp_path / "estado").mkdir()

    assert lock.remove_if_unchanged("qualquer") is False


def test_remove_if_unchanged_backs_off_while_a_fresh_guard_exists(tmp_path: Path) -> None:
    lock, _ = make(tmp_path)
    lock.create_exclusive("meu")
    (tmp_path / "estado" / GUARD_FILE_NAME).write_bytes(b"")
    fresh = lock._clock.now()
    os.utime(tmp_path / "estado" / GUARD_FILE_NAME, (fresh.timestamp(), fresh.timestamp()))

    assert lock.remove_if_unchanged("meu") is False

    assert lock.read() == "meu"


def test_remove_if_unchanged_discards_a_guard_abandoned_long_ago(tmp_path: Path) -> None:
    lock, clock = make(tmp_path)
    lock.create_exclusive("meu")
    guard = tmp_path / "estado" / GUARD_FILE_NAME
    guard.write_bytes(b"")
    old = (clock.now() - timedelta(seconds=GUARD_STALE_SECONDS + 5)).timestamp()
    os.utime(guard, (old, old))

    assert lock.remove_if_unchanged("meu") is True

    assert lock.read() is None
    assert not guard.exists()


def test_create_exclusive_raises_a_config_error_when_the_state_path_is_a_file(
    tmp_path: Path,
) -> None:
    blocker = tmp_path / "estado"
    blocker.write_text("sou um arquivo", encoding="utf-8")
    lock = FileStackLock(blocker, FixedClock(utc(2026, 11, 14)))

    with pytest.raises(ConfigError, match="trava"):
        lock.create_exclusive("x")
