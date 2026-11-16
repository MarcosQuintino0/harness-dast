"""Valida e resume evidência observada, sem inferir qualidade."""

import importlib.util
import math
from collections import Counter, defaultdict
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


def load_local(filename: str, module_name: str) -> Any:
    """Carrega a ferramenta versionada ao lado do resumo."""
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    if spec is None or spec.loader is None:
        raise RuntimeError("comparador indisponível")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Record(BaseModel):
    """Campos externos exigidos pelo resumo; os demais permanecem dados, sem instruções."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    product: str
    mode: Literal["vulnerable", "secure"]
    variant: Literal["A", "B"]
    layer: Literal["t2", "t2-path", "t3", "t4"]
    scan: dict[str, Any]
    rule_stats: dict[str, Any] | None = None
    profile: dict[str, Any] = {}
    proxy_audit: list[dict[str, Any]] = []
    accounts: list[dict[str, Any]] = []
    resource_sampling: dict[str, Any] | None = None
    peak_memory_mib: dict[str, float] = {}
    findings: list[dict[str, Any]] = []

    @field_validator("scan")
    @classmethod
    def validate_scan(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Recusa estruturas aninhadas que não correspondam ao artefato do harness."""
        for key in ("entries", "skipped", "planned"):
            rows = value.get(key, [])
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError(f"{key} inválido")
        policy = value.get("policy")
        if policy is not None and not isinstance(policy, dict):
            raise ValueError("policy inválida")
        return value

    @field_validator("rule_stats")
    @classmethod
    def validate_rule_stats(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Regras desconhecidas não são convertidas em uma lista vazia."""
        if value is None:
            return None
        operations = value.get("operations", [])
        if not isinstance(operations, list) or any(not isinstance(row, dict) for row in operations):
            raise ValueError("operations inválidas")
        for operation in operations:
            rules = operation.get("rules", [])
            if not isinstance(rules, list) or any(not isinstance(rule, dict) for rule in rules):
                raise ValueError("rules inválidas")
        return value

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Limites e escopo devem ser objetos para permitir comparação segura."""
        for key in ("scope", "limits", "scan"):
            if value.get(key) is not None and not isinstance(value[key], dict):
                raise ValueError(f"{key} inválido")
        return value


def pacing_valid(record: Record) -> bool:
    """Exige variante instalada e atraso efetivo observado no resultado do scan."""
    config = record.profile.get("scan")
    limits = record.scan.get("limits")
    if not isinstance(config, dict) or not isinstance(limits, dict):
        return False
    expected = "legacy" if record.variant == "A" else "proxy"
    delay = limits.get("delay_ms")
    if not isinstance(delay, (int, float)) or isinstance(delay, bool):
        return False
    return config.get("pacing") == expected and (delay > 0 if record.variant == "A" else delay == 0)


def duration(scan: dict[str, Any]) -> float | None:
    """Tempo de parede da varredura; data malformada ou fuso ausente é lacuna."""
    try:
        start = datetime.fromisoformat(scan["started_at"])
        end = datetime.fromisoformat(scan["finished_at"])
        if start.utcoffset() is None or end.utcoffset() is None:
            return None
        seconds = (end - start).total_seconds()
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return seconds if math.isfinite(seconds) and seconds > 0 else None


def rule_totals(record: Record) -> dict[str, float] | None:
    """Só totaliza regra quando operação e cada regra foram integralmente medidas."""
    entries = record.scan.get("entries")
    planned = record.scan.get("planned")
    operations = (record.rule_stats or {}).get("operations")
    if record.scan.get("status") != "completed" or not isinstance(entries, list) or not entries:
        return None
    if not isinstance(operations, list) or len(operations) != len(entries):
        return None
    if not isinstance(planned, list) or Counter(
        item.get("operation_id") for item in planned
    ) != Counter(item.get("operation_id") for item in entries):
        return None
    if any(
        not isinstance(e, dict) or e.get("outcome") != "completed" or e.get("truncated")
        for e in entries
    ):
        return None
    expected = Counter(e.get("operation_id") for e in entries)
    if any(not isinstance(op, dict) for op in operations):
        return None
    if Counter(op.get("operation_id") for op in operations) != expected:
        return None
    totals: dict[str, float] = defaultdict(float)
    for operation in operations:
        if not _merge_rules(operation, totals):
            return None
    return dict(totals)


def _merge_rules(operation: dict[str, Any], totals: dict[str, float]) -> bool:
    rules = operation.get("rules")
    if operation.get("unavailable_reason") or not isinstance(rules, list) or not rules:
        return False
    seen: set[int] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            return False
        ident, ms = rule.get("plugin_id"), rule.get("time_ms")
        if (
            not isinstance(ident, int)
            or isinstance(ident, bool)
            or ident in seen
            or rule.get("state") != "completed"
            or not isinstance(ms, (int, float))
            or isinstance(ms, bool)
            or not math.isfinite(ms)
            or ms <= 0
        ):
            return False
        seen.add(ident)
        totals[str(ident)] += ms / 1000
    return True


def audit(record: Record) -> dict[str, Any]:
    """Resume evidência disponível; timestamps e caminhos redigidos não provam a cerca."""
    rows = record.proxy_audit
    allowed = [row for row in rows if row.get("decision") == "allow"]
    hosts = sorted({str(row.get("host")) for row in allowed if row.get("host") is not None})
    methods = sorted({str(row.get("method")) for row in allowed if row.get("method") is not None})
    times: list[datetime] = []
    for row in allowed:
        try:
            stamp = datetime.fromisoformat(row["ts"])
            if stamp.utcoffset() is None:
                times = []
                break
            times.append(stamp)
        except (KeyError, TypeError, ValueError):
            times = []
            break
    times.sort()
    gaps = [(b - a).total_seconds() for a, b in pairwise(times)]
    limit = (record.profile.get("limits") or {}).get("requests_per_second")
    scope = record.profile.get("scope") or {}
    allow = scope.get("allow", [])
    unexpected: list[dict[str, Any]] | None = None
    if (
        isinstance(allow, list)
        and allow
        and all(isinstance(item, dict) and isinstance(item.get("methods"), list) for item in allow)
        and allowed
    ):
        unexpected = []
        for row in allowed:
            if not any(
                row.get("host") == item.get("host")
                and row.get("port") == item.get("port")
                and row.get("method") in item.get("methods", [])
                for item in allow
            ):
                unexpected.append({key: row.get(key) for key in ("host", "port", "method")})
    short_gap: bool | None = None
    if (
        gaps
        and isinstance(limit, (int, float))
        and not isinstance(limit, bool)
        and math.isfinite(limit)
        and limit > 0
    ):
        short_gap = min(gaps) < (1 / limit - 0.001)
    return {
        "rows": len(rows) if rows else None,
        "allowed": len(allowed) if rows else None,
        "denied": len(rows) - len(allowed) if rows else None,
        "hosts": hosts,
        "methods": methods,
        "profile_limit_rps": limit,
        "minimum_gap_seconds": min(gaps) if gaps else None,
        "short_gap_observed": short_gap,
        "unexpected_host_port_method": unexpected,
        "scope_and_rate_status": (
            "requer conferência: trilha redigida não prova forma bruta, janela "
            "nem todos os pontos de concessão"
        ),
    }
