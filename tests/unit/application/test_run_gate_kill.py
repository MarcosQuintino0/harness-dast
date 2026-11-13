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
