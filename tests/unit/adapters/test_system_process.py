"""`SystemProcessProbe` com processos de verdade: o atual, um que terminou e valores absurdos."""

import os
import subprocess
import sys

from harness_dast.adapters.system_process import SystemProcessProbe


def test_current_pid_is_the_pid_of_this_process() -> None:
    assert SystemProcessProbe().current_pid() == os.getpid()


def test_this_process_is_alive() -> None:
    assert SystemProcessProbe().is_alive(os.getpid()) is True


def test_a_finished_child_process_is_not_alive() -> None:
    child = subprocess.Popen([sys.executable, "-I", "-c", "pass"])
    child.wait()

    assert SystemProcessProbe().is_alive(child.pid) is False


def test_a_running_child_process_is_alive_and_the_probe_does_not_kill_it() -> None:
    child = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(30)"])
    try:
        probe = SystemProcessProbe()

        assert probe.is_alive(child.pid) is True
        assert probe.is_alive(child.pid) is True
        assert child.poll() is None
    finally:
        child.kill()
        child.wait()


def test_non_positive_pids_are_not_alive() -> None:
    probe = SystemProcessProbe()

    assert probe.is_alive(0) is False
    assert probe.is_alive(-5) is False
