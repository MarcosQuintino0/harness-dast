"""Conversão conservadora das amostras de CPU e memória, sem Docker."""

from types import SimpleNamespace

import pytest

from tests.integration.v17_resources import ResourceSampler, parse_sample


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("hdast-zap 125.50% 1.5GiB / 2GiB", ("hdast-zap", 125.5, 1536.0)),
        ("hdast-proxy 0% 512KiB / 2GiB", ("hdast-proxy", 0.0, 0.5)),
        ("hdast-zap NaN% -- / --", ("hdast-zap", None, None)),
        ("hdast-zap inf% 1MiB / 2GiB", ("hdast-zap", None, 1.0)),
        ("hdast-zap -1% 0B / 2GiB", ("hdast-zap", None, 0.0)),
        ("outro 99% 1MiB / 2GiB", None),
        ("texto inválido", None),
    ],
)
def test_parser_preserva_unidades_e_ausencias(
    line: str, expected: tuple[str, float | None, float | None] | None
) -> None:
    assert parse_sample(line) == expected


def test_coleta_conta_somente_valores_validos(monkeypatch: pytest.MonkeyPatch) -> None:
    result = SimpleNamespace(
        returncode=0,
        stdout="hdast-zap 1.5% 2MiB / 8GiB\nhdast-proxy NaN% -- / --\n",
    )
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: result)
    sampler = ResourceSampler()
    sampler._sample()
    assert sampler.attempts == 1
    assert sampler.cpu_samples == {"hdast-zap": 1}
    assert sampler.memory_samples == {"hdast-zap": 1}
    assert sampler.cpu_peaks == {"hdast-zap": 1.5}
    assert sampler.peaks == {"hdast-zap": 2}
