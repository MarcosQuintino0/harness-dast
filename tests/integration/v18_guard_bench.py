"""Mede a porta real e o custo mínimo de metadados dentro do proxy de laboratório."""

import hashlib
import inspect
import json
import platform
import statistics
import time
from collections.abc import Callable
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from harness_dast.adapters.scope_proxy import approval_watch, engine, gate
from harness_dast.adapters.scope_proxy.decision import Reason
from harness_dast.adapters.scope_proxy.policy import load_policy

SAMPLES = 1000
WARMUP = 100
policy_path = Path("/policy/policy.json")
policy = load_policy(policy_path)
assert policy.binding is not None
kill = policy_path.parent / "KILL"
approval = Path("/approvals") / (policy.binding.product + ".json")
profile = Path("/product/target.yml")


def clock() -> datetime:
    return datetime.now(UTC)


proxy_engine = engine.ScopeProxyEngine(
    policy,
    policy_dir=policy_path.parent,
    audit_file=StringIO(),
    stdout=StringIO(),
    now=clock,
    monotonic=time.monotonic,
)
run_gate = proxy_engine._gate


def stat_only() -> None:
    """Simula identidade mínima dos dois arquivos e a consulta do sinal de parada."""
    kill.parent.stat()
    try:
        kill.lstat()
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("kill presente")
    for path in (approval, profile):
        value = path.stat()
        _ = value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def measure(fn: Callable[[], Reason | None]) -> dict[str, object]:
    samples = []
    for i in range(WARMUP + SAMPLES):
        start = time.perf_counter_ns()
        result = fn()
        elapsed = time.perf_counter_ns() - start
        assert result is None, "porta recusou: medição inválida"
        if i >= WARMUP:
            samples.append(elapsed)
        # Espera fora da fatia cronometrada, igual no before e no after, para observar
        # múltiplos ciclos caso a composição real passe a usar uma vigia.
        time.sleep(0.002)
    ordered = sorted(samples)
    return {
        "samples_ns": samples,
        "median_ms": statistics.median(samples) / 1e6,
        "p25_ms": ordered[249] / 1e6,
        "p75_ms": ordered[749] / 1e6,
        "p95_ms": ordered[949] / 1e6,
        "min_ms": ordered[0] / 1e6,
        "max_ms": ordered[-1] / 1e6,
    }


def sha(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


assert run_gate._detect() is None, "porta recusou antes da medição"
detect = measure(run_gate._detect)
assert run_gate._detect() is None, "porta recusou depois da medição"
stat = measure(stat_only)
assert run_gate._detect() is None, "porta recusou depois da simulação"
print(  # noqa: T201 - JSON pelo stdout para o executor
    json.dumps(
        {
            "run_id": policy.run_id,
            "product": policy.binding.product,
            "recorded_utc": clock().isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "warmup": WARMUP,
            "samples": SAMPLES,
            "source_sha256": {
                "gate": sha(inspect.getfile(gate)),
                "engine": sha(inspect.getfile(engine)),
                "approval_watch": sha(inspect.getfile(approval_watch)),
                "policy": sha(policy_path),
                "approval": sha(approval),
                "profile": sha(profile),
            },
            "detect": detect,
            "stat_only": stat,
        },
        ensure_ascii=False,
    )
)
