"""Mede apenas o processo da CLI; não inclui ZAP, proxy ou processos filhos."""

import ctypes
import importlib
import sys
import time
from ctypes import wintypes


class _MemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _peak_memory() -> int | None:
    platform = sys.platform
    if platform == "win32":
        windows = getattr(ctypes, "windll", None)
        if windows is None:
            return None
        kernel = windows.kernel32
        psapi = windows.psapi
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(_MemoryCounters),
            wintypes.DWORD,
        )
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = _MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            return None
        return int(counters.PeakWorkingSetSize)
    try:
        resource = importlib.import_module("resource")
    except ImportError:
        return None
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if platform == "darwin" else peak * 1024


class SystemProcessSampler:
    """CPU acumulada e pico residente desde o início da CLI, não apenas do scan."""

    def sample(self) -> tuple[float, int | None]:
        """Amostra CPU e pico; memória ausente fica None."""
        return time.process_time(), _peak_memory()
