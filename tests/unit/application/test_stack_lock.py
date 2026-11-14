"""`StackLockService`: segunda execução recusada, soltura sempre, órfã retomada, viva respeitada."""

from datetime import timedelta

import pytest

from harness_dast.application.stack_lock import StackLockService
from harness_dast.domain.errors import ConfigError, ExitCode, StackBusy
from harness_dast.domain.stack_lock import LockHolder, render_lock
from tests.fakes.clock import FixedClock, utc
from tests.fakes.stack import CountingRandom
from tests.fakes.stack_lock import FakeProcesses, InMemoryLockFile

NOW = utc(2026, 11, 14, 10, 0)
OTHER_PID = 777


def planted(pid: int = OTHER_PID, command: str = "scan") -> str:
    return render_lock(
        LockHolder(
            lock_id="0000000000ff",
            command=command,
            product="outro",
            pid=pid,
            started_at=NOW - timedelta(minutes=7),
        )
    )


class Rig:
    def __init__(self, content: str | None = None, *, alive: set[int] | None = None) -> None:
        self.file = InMemoryLockFile(content)
        self.processes = FakeProcesses(pid=4242, alive=alive)
        self.clock = FixedClock(NOW)
        self.service = StackLockService(
            store=self.file, clock=self.clock, processes=self.processes, random=CountingRandom()
        )


def test_hold_creates_the_lock_with_the_owner_and_releases_it_when_the_block_ends() -> None:
    rig = Rig()

    with rig.service.hold("probe", "demo") as holder:
        assert rig.file.content == render_lock(holder)
        assert (holder.command, holder.product, holder.pid) == ("probe", "demo", 4242)
        assert holder.started_at == NOW

    assert rig.file.content is None


def test_second_hold_is_refused_with_who_holds_and_the_first_keeps_its_lock() -> None:
    rig = Rig()

    with rig.service.hold("run", "demo") as first:
        with pytest.raises(StackBusy) as raised, rig.service.hold("probe", "demo"):
            pytest.fail("a segunda execução não podia entrar")
        assert rig.file.content == render_lock(first)

    error = raised.value
    assert error.code == "STACK_BUSY"
    assert error.exit_code == ExitCode.BUSY
    assert "`run`" in error.message
    assert first.lock_id in error.message
    assert error.hint is not None
    assert "hdast stop" in error.hint


def test_lock_is_released_when_the_block_raises() -> None:
    rig = Rig()

    with pytest.raises(ConfigError), rig.service.hold("scan", "demo"):
        raise ConfigError("perfil inválido")

    assert rig.file.content is None


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_lock_is_released_when_the_block_is_interrupted(
    interruption: type[BaseException],
) -> None:
    rig = Rig()

    with pytest.raises(interruption), rig.service.hold("run", "demo"):
        raise interruption

    assert rig.file.content is None


def test_a_failed_release_does_not_mask_the_error_of_the_block() -> None:
    rig = Rig()

    rig.file.fail_release = True

    with pytest.raises(RuntimeError, match="do bloco"), rig.service.hold("scan", "demo"):
        raise RuntimeError("erro do bloco")


def test_the_lock_can_be_taken_again_after_it_was_released() -> None:
    rig = Rig()
    with rig.service.hold("probe", "demo"):
        pass

    with rig.service.hold("scan", "demo") as holder:
        assert holder.command == "scan"


def test_an_orphan_lock_is_taken_over_when_the_owner_process_is_dead() -> None:
    rig = Rig(planted(), alive=set())

    with rig.service.hold("probe", "demo") as holder:
        assert rig.file.content == render_lock(holder)
        assert rig.file.content != planted()

    assert rig.file.content is None


def test_a_lock_of_a_live_process_is_respected_and_never_deleted() -> None:
    rig = Rig(planted(), alive={OTHER_PID})

    with pytest.raises(StackBusy) as raised, rig.service.hold("probe", "demo"):
        pytest.fail("não podia entrar")

    assert rig.file.content == planted()
    assert rig.file.removals == 0
    assert str(OTHER_PID) in raised.value.message


@pytest.mark.parametrize(
    "content",
    ["", "   ", "{", "não é json", "[]", '{"pid": 1}', "\x00\x01\x02"],
)
def test_an_empty_corrupt_or_malformed_lock_fails_closed_and_is_left_alone(
    content: str,
) -> None:
    rig = Rig(content)

    with pytest.raises(StackBusy) as raised, rig.service.hold("probe", "demo"):
        pytest.fail("não podia entrar")

    assert rig.file.content == content
    assert raised.value.hint is not None
    assert "hdast stack status" in raised.value.hint


def test_a_lock_replaced_by_another_run_while_taking_over_is_not_deleted() -> None:
    """Corrida: outra execução retoma a órfã antes e já é a dona viva quando esta relê."""
    rig = Rig(planted(), alive=set())
    winner = planted(pid=OTHER_PID, command="authz")
    original_remove = rig.file.remove_if_unchanged

    def lose_the_race(expected: str) -> bool:
        rig.file.content = winner  # a outra execução trocou a trava
        rig.processes.alive.add(OTHER_PID)
        return original_remove(expected)

    rig.file.remove_if_unchanged = lose_the_race  # type: ignore[method-assign]  # injeta a corrida

    with pytest.raises(StackBusy) as raised, rig.service.hold("probe", "demo"):
        pytest.fail("não podia entrar")

    assert rig.file.content == winner
    assert "`authz`" in raised.value.message


def test_inspect_is_none_when_the_stack_is_free() -> None:
    assert Rig().service.inspect() is None


def test_inspect_describes_a_held_lock() -> None:
    rig = Rig(planted(), alive={OTHER_PID})

    info = rig.service.inspect()

    assert info is not None
    assert (info.state, info.command, info.product, info.pid) == ("held", "scan", "outro", 777)
    assert info.lock_id == "0000000000ff"
    assert "há 7 min" in info.message


def test_inspect_describes_an_orphan_lock() -> None:
    info = Rig(planted(), alive=set()).service.inspect()

    assert info is not None
    assert info.state == "orphan"
    assert "órfã" in info.message


@pytest.mark.parametrize("content", ["", "lixo"])
def test_inspect_describes_an_unreadable_lock(content: str) -> None:
    info = Rig(content).service.inspect()

    assert info is not None
    assert info.state == "unreadable"
    assert info.command is None
    assert "hdast stack status" in info.message
