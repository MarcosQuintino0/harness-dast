"""Implementações reais de espera e aleatoriedade."""

import re
import time

from harness_dast.adapters.system_runtime import SystemEntropy, SystemSleeper


def test_hex_suffix_has_four_lowercase_hex_digits_and_varies() -> None:
    entropy = SystemEntropy()

    values = {entropy.hex_suffix() for _ in range(50)}

    assert all(re.fullmatch(r"[0-9a-f]{4}", v) for v in values)
    assert len(values) > 1


def test_seed_is_a_non_negative_32_bit_integer() -> None:
    seeds = [SystemEntropy().seed() for _ in range(20)]

    assert all(0 <= s < 2**32 for s in seeds)
    assert len(set(seeds)) > 1


def test_sleeper_waits_and_treats_negative_as_zero() -> None:
    sleeper = SystemSleeper()
    start = time.perf_counter()

    sleeper.sleep(0.05)
    sleeper.sleep(-5)

    assert 0.04 <= time.perf_counter() - start < 1.0
