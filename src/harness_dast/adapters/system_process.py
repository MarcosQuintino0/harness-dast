"""Implementação real da porta `ProcessProbe`: PID atual e "este processo está vivo?".

No POSIX, `os.kill(pid, 0)` só confere a existência. No Windows, `os.kill` com sinal 0 ENCERRA o
processo, então a consulta usa `OpenProcess` e `GetExitCodeProcess` (via `ctypes`).
Na dúvida (sem permissão para consultar), responde que está vivo: a trava nunca é retomada por
engano.
"""

import os
import sys

_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_ACCESS_DENIED = 5


class SystemProcessProbe:
    """Consulta processos do sistema operacional."""

    def current_pid(self) -> int:
        """Número do processo em execução."""
        return os.getpid()

    def is_alive(self, pid: int) -> bool:
        """Se existe um processo vivo com esse número (`True` na dúvida)."""
        if pid <= 0:
            return False
        return _windows_alive(pid) if sys.platform == "win32" else _posix_alive(pid)


def _posix_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe, só não é nosso
    except OSError:
        return True
    return True


def _windows_alive(pid: int) -> bool:
    alive = True  # na dúvida, vivo
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            # Sem permissão: o processo existe. Qualquer outro erro: o PID não existe.
            alive = ctypes.get_last_error() == _ERROR_ACCESS_DENIED
        else:
            try:
                code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    alive = code.value == _STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
    return alive
