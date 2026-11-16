"""Resume evidências V1.7 e prepara entradas de previsão sem aprovar qualidade."""

import argparse
import hashlib
import importlib.util
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from runpy import run_path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

_NAME = re.compile(r"^v17-(t2-path|t2|t3|t4)-(.+)-(vulnerable|secure)-([1-5])-([AB])\.json$")
_MATRIX = run_path(str(Path(__file__).resolve().parents[3] / "tests/integration/v17_matrix.py"))
PILOT = tuple(_MATRIX["PILOT"])
VAMPI = tuple(_MATRIX["VAMPI"])


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


def _load_local(filename: str, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    if spec is None or spec.loader is None:
        raise RuntimeError("comparador indisponível")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _valid_pairs(records: dict[tuple[str, int, str], Record], indices: list[int]) -> bool:
    comparator = _load_local("compare.py", "v17_compare")
    for index in indices:
        first, second = records.get(("t3", index, "A")), records.get(("t3", index, "B"))
        if first is None or second is None:
            return False
        # A comparação sempre inclui a ressalva de qualidade que depende de revisão humana.
        issues = comparator.compare(first.model_dump(), second.model_dump())["issues"]
        if len(issues) != 1 or not issues[0].startswith("pontos de injeção"):
            return False
    return True


def _sample_values(
    record: Record | None, base: Record, full: dict[str, float]
) -> dict[str, float] | None:
    if record is None:
        return None
    values = rule_totals(record)
    expected = set(
        PILOT if base.product == "clinica-piloto" else VAMPI if base.product == "vampi" else ()
    )
    if not values or values.keys() != full.keys() or not expected:
        return None
    if {entry.get("operation_id") for entry in record.scan["entries"]} != expected:
        return None
    if (
        record.scan.get("policy") != base.scan.get("policy")
        or record.profile.get("scope") != base.profile.get("scope")
        or record.profile.get("limits") != base.profile.get("limits")
    ):
        return None
    return values


def _baseline(records: dict[tuple[str, int, str], Record]) -> Record | None:
    if ("t4", 1, "B") in records:
        return None
    base = records.get(("t4", 1, "A"))
    if base is None:
        return None
    uncertain = {"not_run", "not_learned", "not_planned", "not_success"}
    if any(item.get("reason") in uncertain for item in base.scan.get("skipped", [])):
        return None
    return base


def prediction_input(records: dict[tuple[str, int, str], Record]) -> dict[str, Any] | None:
    """Constrói insumo só com T4 A e 3 ou 5 pares completos e mesmo inventário."""
    base = _baseline(records)
    if base is None:
        return None
    indices = sorted({i for layer, i, _ in records if layer == "t3"})
    if indices not in ([1, 2, 3], [1, 2, 3, 4, 5]) or not _valid_pairs(records, indices):
        return None
    full, wall = rule_totals(base), duration(base.scan)
    if not full or wall is None:
        return None
    if (
        not base.profile.get("scope")
        or not base.profile.get("limits")
        or not base.scan.get("policy")
    ):
        return None
    samples: dict[str, dict[str, list[float]]] = {key: {"A": [], "B": []} for key in full}
    for index in indices:
        for variant in ("A", "B"):
            record = records.get(("t3", index, variant))
            values = _sample_values(record, base, full)
            if values is None:
                return None
            for key, value in values.items():
                samples[key][variant].append(value)
    return {
        "wall_a": wall,
        "expected_rule_ids": sorted(full),
        "rules": {
            key: {
                "full_a": full[key],
                "t3_a": samples[key]["A"],
                "t3_b": samples[key]["B"],
                "complete": True,
            }
            for key in sorted(full)
        },
    }


def _load_groups(
    folder: Path,
) -> tuple[
    dict[tuple[str, str], dict[tuple[str, int, str], Record]],
    list[dict[str, str]],
    set[tuple[str, str]],
]:
    groups: dict[tuple[str, str], dict[tuple[str, int, str], Record]] = defaultdict(dict)
    invalid: list[dict[str, str]] = []
    duplicate_groups: set[tuple[str, str]] = set()
    for path in sorted(folder.glob("v17*.json")):
        match = _NAME.fullmatch(path.name)
        if match is None:
            invalid.append({"file": path.name, "reason": "nome não reconhecido"})
            continue
        layer, product, mode, number, variant = match.groups()
        try:
            record = Record.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError):
            invalid.append({"file": path.name, "reason": "registro inválido ou ilegível"})
            duplicate_groups.add((product, mode))
            continue
        if (record.layer, record.product, record.mode, record.variant) != (
            layer,
            product,
            mode,
            variant,
        ):
            invalid.append({"file": path.name, "reason": "metadados divergentes"})
            duplicate_groups.add((product, mode))
            continue
        group = (product, mode)
        key = (layer, int(number), variant)
        if key in groups[group]:
            duplicate_groups.add(group)
            invalid.append({"file": path.name, "reason": "registro duplicado"})
        groups[group][key] = record
    return groups, invalid, duplicate_groups


def _confirmation(records: dict[tuple[str, int, str], Record], frozen: Any) -> dict[str, Any]:
    outcome: dict[str, Any] = {
        "status": "inconclusivo",
        "reason": "previsão congelada ou T4 ausente",
    }
    if (
        not isinstance(frozen, dict)
        or not isinstance(frozen.get("input"), dict)
        or not isinstance(frozen.get("result"), dict)
    ):
        return outcome
    payload = {"input": frozen["input"], "result": frozen["result"]}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != frozen.get("sha256"):
        return {"status": "inconclusivo", "reason": "hash da previsão divergente"}
    baseline, changed = records.get(("t4", 1, "A")), records.get(("t4", 1, "B"))
    if baseline is None or changed is None:
        return outcome
    a, b = duration(baseline.scan), duration(changed.scan)
    predicted = frozen["result"].get("gain_pct")
    if (
        a is None
        or b is None
        or frozen["input"].get("wall_a") != a
        or not isinstance(predicted, (int, float))
        or isinstance(predicted, bool)
        or not math.isfinite(predicted)
    ):
        return outcome
    observed = 100 * (a - b) / a
    return {
        "status": "inconclusivo: qualidade requer conferência",
        "observed_gain_pct": observed,
        "predicted_gain_pct": predicted,
        "difference_pp": abs(observed - predicted),
        "within_10pp_descriptive": abs(observed - predicted) <= 10,
    }


def summarize(
    folder: Path, frozen: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Organiza fatos observados; não transforma observações em aceite de qualidade."""
    groups, invalid, duplicate_groups = _load_groups(folder)
    output: dict[str, Any] = {
        "status": "inconclusivo",
        "quality_accepted": False,
        "invalid": invalid,
        "groups": {},
    }
    predictions: dict[str, Any] = {}
    comparator = _load_local("compare.py", "v17_compare")
    estimator = _load_local("analyze.py", "v17_analyze")
    for (product, mode), records in sorted(groups.items()):
        name = f"{product}/{mode}"
        rows: dict[str, Any] = {}
        pairs: list[dict[str, Any]] = []
        for (layer, index, variant), record in sorted(records.items()):
            row_key = f"{layer}-{index}-{variant}"
            totals = rule_totals(record)
            rows[row_key] = {
                "scan_seconds": duration(record.scan),
                "scan_status": record.scan.get("status"),
                "skips": record.scan.get("skipped"),
                "rules_complete": totals is not None,
                "rule_count": len(totals) if totals is not None else None,
                "findings": record.findings,
                "audit": audit(record),
                "resource_sampling": record.resource_sampling,
                "peak_memory_mib": record.peak_memory_mib or None,
            }
        for index in sorted({i for layer, i, _ in records if layer == "t3"}):
            a, b = records.get(("t3", index, "A")), records.get(("t3", index, "B"))
            if a is None or b is None:
                pairs.append({"index": index, "gain_pct_observed": None, "issues": ["par ausente"]})
                continue
            a_seconds, b_seconds = duration(a.scan), duration(b.scan)
            gain = 100 * (a_seconds - b_seconds) / a_seconds if a_seconds and b_seconds else None
            check = comparator.compare(a.model_dump(), b.model_dump())
            if gain is None:
                check["issues"].append("duração ausente ou inválida")
            pairs.append({"index": index, "gain_pct_observed": gain, "issues": check["issues"]})
        gains = [
            pair["gain_pct_observed"] for pair in pairs if pair["gain_pct_observed"] is not None
        ]
        output["groups"][name] = {
            "runs": rows,
            "pairs": pairs,
            "median_pct_descriptive": statistics.median(gains) if gains else None,
            "range_pp_descriptive": max(gains) - min(gains) if gains else None,
            "mixed_signs": min(gains) < 0 < max(gains) if gains else None,
            "quality_status": "inconclusivo: requer aferição independente",
            "t4_confirmation": _confirmation(records, (frozen or {}).get(name)),
        }
        prediction = None if (product, mode) in duplicate_groups else prediction_input(records)
        if prediction is not None:
            result = estimator.predict(prediction)
            frozen = {"input": prediction, "result": result}
            canonical = json.dumps(
                frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            predictions[name] = {
                **frozen,
                "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            }
    return output, predictions


def main() -> None:
    """Lê pasta e grava o resumo e os insumos congeláveis sem sobrescrever arquivos."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prediction-output", type=Path, required=True)
    parser.add_argument("--frozen-prediction", type=Path)
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error("diretório de registros inexistente")
    if (
        args.output.exists()
        or args.prediction_output.exists()
        or args.output == args.prediction_output
    ):
        parser.error("destinos devem ser distintos e ainda não existir")
    frozen = None
    if args.frozen_prediction is not None:
        loaded = json.loads(args.frozen_prediction.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            parser.error("previsão congelada inválida")
        frozen = loaded
    summary, predictions = summarize(args.directory, frozen)
    for path, value in ((args.output, summary), (args.prediction_output, predictions)):
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")


if __name__ == "__main__":
    main()
