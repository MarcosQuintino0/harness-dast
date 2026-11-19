"""Amostra CPU e memória dos contêineres locais em uma única consulta periódica."""

import math
import re
import shutil
import subprocess
import threading
import time
from typing import Self

import httpx

from tests.integration.lab_support import ZapView
from tests.integration.zap_scan_readback_support import ZapReadbackApiError, sample_zap

_LINE = re.compile(r"^(\S+)\s+(\S+)\s+(\S+)\s*/")
_MEMORY = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(B|KiB|MiB|GiB)$")
_UNITS = {"B": 1 / 1048576, "KiB": 1 / 1024, "MiB": 1.0, "GiB": 1024.0}


def parse_sample(line: str) -> tuple[str, float | None, float | None] | None:
    """Devolve nome e métricas válidas; dado ausente não vira zero."""
    found = _LINE.match(line)
    if found is None or not found[1].startswith("hdast"):
        return None
    cpu_text = found[2]
    cpu: float | None = None
    if cpu_text.endswith("%"):
        try:
            value = float(cpu_text[:-1])
        except ValueError:
            value = float("nan")
        if math.isfinite(value) and value >= 0:
            cpu = value
    mem = _MEMORY.fullmatch(found[3])
    memory = float(mem[1]) * _UNITS[mem[2]] if mem else None
    if memory is not None and not math.isfinite(memory):
        memory = None
    return found[1], cpu, memory


class ResourceSampler:
    """Picos e contagens amostrados; CPU percentual não representa CPU acumulada."""

    def __init__(self, interval: float = 15.0, *, zap: ZapView | None = None) -> None:
        self.interval = interval
        self.peaks: dict[str, float] = {}
        self.cpu_peaks: dict[str, float] = {}
        self.cpu_samples: dict[str, int] = {}
        self.memory_samples: dict[str, int] = {}
        self.attempts = 0
        self.seconds = 0.0
        self.complete = False
        self.zap_attempts = 0
        self.zap_unavailable = 0
        self.zap_errors: dict[str, int] = {}
        self.zap_idle = 0
        self.zap_samples: list[dict[str, object]] = []
        self._zap = zap
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._started = 0.0

    def __enter__(self) -> Self:
        self._started = time.monotonic()
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=50)
        self.complete = not self._thread.is_alive()
        self.seconds = time.monotonic() - self._started

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._sample_zap()
            self._stop.wait(self.interval)

    def _sample_zap(self) -> None:
        if self._zap is None:
            return
        self.zap_attempts += 1
        try:
            sample = sample_zap(self._zap)
        except httpx.HTTPStatusError as error:
            self._zap_error(f"http_{error.response.status_code}")
            return
        except (httpx.RequestError, OSError):
            self._zap_error("transport")
            return
        except httpx.HTTPError:
            self._zap_error("http_error")
            return
        except ZapReadbackApiError:
            self._zap_error("api_error")
            return
        except (ValueError, TypeError):
            self._zap_error("invalid_format")
            return
        if sample is None:
            self.zap_idle += 1
        else:
            self.zap_samples.append(sample)

    def _zap_error(self, code: str) -> None:
        self.zap_unavailable += 1
        self.zap_errors[code] = self.zap_errors.get(code, 0) + 1

    def _sample(self) -> None:
        self.attempts += 1
        try:
            result = subprocess.run(  # noqa: S603 - comando fixo de diagnóstico local
                [
                    shutil.which("docker") or "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.Name}} {{.CPUPerc}} {{.MemUsage}}",
                ],
                capture_output=True,
                text=True,
                timeout=40,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return
        if result.returncode:
            return
        for line in result.stdout.splitlines():
            parsed = parse_sample(line)
            if parsed is None:
                continue
            name, cpu, memory = parsed
            if cpu is not None:
                self.cpu_samples[name] = self.cpu_samples.get(name, 0) + 1
                self.cpu_peaks[name] = max(self.cpu_peaks.get(name, 0.0), cpu)
            if memory is not None:
                self.memory_samples[name] = self.memory_samples.get(name, 0) + 1
                self.peaks[name] = max(self.peaks.get(name, 0.0), memory)
