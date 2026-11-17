"""Diagnóstico isolado da vigia, sem tráfego e sem exportar conteúdo das fontes.

Execute dentro da imagem do proxy, com os caminhos montados fornecidos pelo coordenador.
O processo cria sua própria vigia: não altera nem observa o estado interno do proxy real.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from threading import Lock

from harness_dast.adapters.scope_proxy.approval_watch import FileWatch, file_signature
from harness_dast.adapters.scope_proxy.decision import Reason
from harness_dast.adapters.scope_proxy.gate_watch import GateWatch
from harness_dast.adapters.scope_proxy.policy import load_policy
from harness_dast.domain.errors import ConfigError


def inspect_metadata(path: Path) -> dict[str, bool]:
    """Compara metadados antes/depois de leitura e com o caminho, sem publicá-los."""
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            handle.read(1024 * 1024 + 1)
            after = os.fstat(handle.fileno())
        current = path.stat()
        return {
            "accessible": True,
            "descriptor_stable": file_signature(before) == file_signature(after),
            "path_matches_descriptor": file_signature(after) == file_signature(current),
            "device_matches_descriptor": after.st_dev == current.st_dev,
            "inode_matches_descriptor": after.st_ino == current.st_ino,
            "size_matches_descriptor": after.st_size == current.st_size,
            "mtime_matches_descriptor": after.st_mtime_ns == current.st_mtime_ns,
            "ctime_matches_descriptor": after.st_ctime_ns == current.st_ctime_ns,
        }
    except OSError:
        return {"accessible": False}


def diagnose(
    policy_path: Path, approval_dir: Path, profile_dir: Path, seconds: float
) -> dict[str, object]:
    """Mede uma vigia independente com as fontes montadas, sem retornar dados sensíveis."""
    try:
        binding = load_policy(policy_path).binding
    except ConfigError:
        return {"policy_valid": False}
    if binding is None:
        return {"policy_valid": True, "binding_present": False}
    approval = approval_dir / f"{binding.product}.json"
    profile = profile_dir / "target.yml"
    watches = (
        FileWatch(approval, binding.approval_sha256, product=binding.product),
        FileWatch(profile, binding.profile_sha256),
    )
    events: list[dict[str, float | bool]] = []
    lock = Lock()
    origin = time.monotonic()

    def detect() -> Reason | None:
        start = time.monotonic()
        try:
            policy_path.parent.stat()
            try:
                (policy_path.parent / "KILL").lstat()
            except FileNotFoundError:
                stopped = False
            else:
                stopped = True
        except OSError:
            stopped = True
        approval_ok = watches[0].unchanged()
        profile_ok = watches[1].unchanged()
        with lock:
            events.append(
                {
                    "start_ms": (start - origin) * 1000,
                    "duration_ms": (time.monotonic() - start) * 1000,
                    "stop_or_inaccessible": stopped,
                    "approval_unchanged": approval_ok,
                    "profile_unchanged": profile_ok,
                }
            )
        if stopped:
            return Reason.KILL_SWITCH
        return None if approval_ok and profile_ok else Reason.APPROVAL_CHANGED

    watch = GateWatch(detect, time.monotonic)
    rejected_at_ms: float | None = None
    try:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if watch.check() is not None and rejected_at_ms is None:
                rejected_at_ms = (time.monotonic() - origin) * 1000
            time.sleep(0.01)
    finally:
        watch.close()
    with lock:
        captured = list(events)
    return {
        "policy_valid": True,
        "binding_present": True,
        "rejected_at_ms": rejected_at_ms,
        "approval_metadata": inspect_metadata(approval),
        "profile_metadata": inspect_metadata(profile),
        "checks": captured,
    }


def main() -> None:
    """Executa somente o diagnóstico local e escreve JSON sanitizado na saída padrão."""
    parser = argparse.ArgumentParser()
    parser.add_argument("policy", type=Path)
    parser.add_argument("approvals", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--seconds", type=float, default=10.0)
    args = parser.parse_args()
    if not 0 < args.seconds <= 60:
        parser.error("seconds deve estar entre zero e 60")
    sys.stdout.write(json.dumps(diagnose(args.policy, args.approvals, args.profile, args.seconds)))


if __name__ == "__main__":
    main()
