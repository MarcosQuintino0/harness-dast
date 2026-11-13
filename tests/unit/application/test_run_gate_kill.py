"""`RunGate`: a trava de emergência para o envio antes de janela e prazo."""

import pytest

from harness_dast.application.run_support import KillSwitchEngaged, RunGate, WindowClosed
from tests.fakes.clock import FixedClock, utc
from tests.fakes.profile_data import valid_profile


class _Kill:
    def __init__(self, on: bool) -> None:
        self.on = on

    def engaged(self) -> bool:
        return self.on


def test_gate_raises_kill_switch_engaged_when_the_switch_is_on() -> None:
    clock = FixedClock(utc(2026, 11, 13, 10))
    gate = RunGate(valid_profile(), clock, clock.now(), _Kill(on=True))

    with pytest.raises(KillSwitchEngaged, match="hdast stop"):
        gate.check()


def test_kill_switch_engaged_is_a_window_closed_so_every_stage_stops_the_same_way() -> None:
    assert issubclass(KillSwitchEngaged, WindowClosed)


def test_gate_passes_when_the_switch_is_off() -> None:
    clock = FixedClock(utc(2026, 11, 13, 10))
    gate = RunGate(valid_profile(), clock, clock.now(), _Kill(on=False))

    gate.check()


def test_gate_deadline_inherited_from_the_run_can_only_shorten_the_profile_deadline() -> None:
    from datetime import timedelta

    from harness_dast.application.run_support import DeadlineReached

    clock = FixedClock(utc(2026, 11, 13, 10))
    profile = valid_profile()
    own = clock.now() + timedelta(minutes=profile.limits.max_duration_minutes)
    shorter = RunGate(
        profile, clock, clock.now(), None, deadline=clock.now() + timedelta(minutes=2)
    )
    longer = RunGate(profile, clock, clock.now(), None, deadline=own + timedelta(hours=5))

    clock.advance_to(clock.now() + timedelta(minutes=3))

    with pytest.raises(DeadlineReached):
        shorter.check()
    longer.check()  # o prazo herdado não amplia o do perfil
