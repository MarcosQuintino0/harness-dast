"""Construtores compartilhados pelos testes do proxy de escopo."""

import copy
import json
from typing import Any

from harness_dast.adapters.scope_proxy.policy import ProxyPolicy, parse_policy

BASE_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "run_id": "2026-11-13T00-00-00Z-lab-0001",
    "scope": {
        "allow": [
            {
                "host": "api.exemplo.com",
                "paths": ["/api/**"],
                "methods": ["GET", "POST"],
            },
            {
                "host": "vampi",
                "scheme": "http",
                "port": 5000,
                "allow_local": True,
                "paths": ["/users/**"],
                "methods": ["GET"],
            },
        ],
        "deny_paths": ["/api/admin/**"],
    },
    "limits": {"requests_per_second": 10, "max_duration_minutes": 60, "zap_threads_per_host": 2},
    "not_after": "2030-01-01T00:00:00Z",
}


def policy_data(**changes: Any) -> dict[str, Any]:
    """Cópia profunda da política base com campos de topo substituídos."""
    data = copy.deepcopy(BASE_POLICY)
    data.update(changes)
    return data


def make_policy(**changes: Any) -> ProxyPolicy:
    return parse_policy(json.dumps(policy_data(**changes)).encode())
