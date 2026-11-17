"""Medição privada e conservadora da classificação por execução e fingerprint."""

import json
import re
from collections import Counter
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from evals.runner.cases import EvalError, load_case
from evals.runner.checks_findings import matches
from evals.runner.models import Case, Flaw, Matcher
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.triage import TriageFile
from harness_dast.domain.verification import VerificationFile

# O gabarito identifica as operacoes e os parametros corrigidos pelo modo seguro.
PILOT_CORRECTED = MappingProxyType(
    {
        "H1": ("GET", "/api/pacientes/busca", "nome"),
        "H4": ("GET", "/api/documentos/download", "arquivo"),
    }
)


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _version(data: object, field: str = "schema_version") -> None:
    if not isinstance(data, dict) or type(data.get(field)) is not int or data[field] != 1:
        raise ValueError(f"{field} ausente ou incompatível")


def _report(path: Path, case: Case) -> list[dict[str, Any]]:
    data = _read(path)
    _version(data)
    _version(data, "fingerprint_version")
    report = FindingsReport.model_validate_json(json.dumps(data), strict=True)
    if report.run_id != path.parent.name or report.product != case.product:
        raise ValueError("contexto do relatório divergente")
    rows = [item.model_dump() for item in report.findings]
    for section in (report.authz, report.proxy_signals, report.negative):
        if section is not None:
            rows.extend(item.model_dump() for item in section.findings)
    fingerprints = [row["fingerprint"] for row in rows]
    if any(
        type(row.get("fingerprint_version")) is not int
        or row["fingerprint_version"] != (2 if row.get("origin") == "proxy" else 1)
        for row in rows
    ):
        raise ValueError("versão de fingerprint do achado incompatível")
    if any(not re.fullmatch(r"[0-9a-f]{64}", fp) for fp in fingerprints):
        raise ValueError("fingerprint invalido no relatorio")
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("fingerprint repetido no relatório")
    return rows


def _specific(matcher: Matcher) -> bool:
    return bool(
        (matcher.path_contains or matcher.operation_id)
        and (matcher.titles or matcher.technique or matcher.category)
    )


def _known_pilot_flaw(case: Case, flaw: Flaw) -> bool:
    try:
        original = load_case("clinica-piloto")
    except (EvalError, OSError, UnicodeError):
        return False
    return case.target == original.target and flaw in original.flaws


def _truth(case: Case, mode: str, finding: dict[str, Any]) -> tuple[str, str, str]:
    hits: list[Flaw] = []
    partial = False
    for flaw in case.flaws:
        full = ((flaw.match,) if flaw.match else ()) + flaw.match_any
        if any(_specific(m) and matches(finding, m) for m in full):
            hits.append(flaw)
        if any(not _specific(m) and matches(finding, m) for m in full):
            partial = True
        if flaw.partial and matches(finding, flaw.partial):
            partial = True
    if len(hits) != 1 or partial:
        return (
            "unknown",
            "indeterminado",
            "gabarito parcial, sem correspondência específica ou ambíguo",
        )
    flaw = hits[0]
    if mode == "vulnerable":
        return flaw.id, "real", "correspondência específica com falha do gabarito"
    if (
        mode == "secure"
        and case.name == "clinica-piloto"
        and flaw.id in PILOT_CORRECTED
        and _known_pilot_flaw(case, flaw)
        and (finding.get("method"), finding.get("path_template"), finding.get("parameter"))
        == PILOT_CORRECTED[flaw.id]
    ):
        return flaw.id, "false", "falha corrigida no modo seguro segundo o gabarito"
    return flaw.id, "indeterminado", "correção no modo seguro não demonstrada no gabarito aplicável"


def _load_triage(path: Path) -> tuple[TriageFile, set[str]]:
    data = _read(path)
    _version(data)
    result = TriageFile.model_validate_json(json.dumps(data), strict=True)
    if not isinstance(data, dict):
        raise TypeError("triagem invalida")
    declared = {
        item["fingerprint"] for item in data["annotations"] if "suspected_false_positive" in item
    }
    return result, declared


def _load_verification(path: Path, case: Case) -> VerificationFile:
    data = _read(path)
    _version(data)
    result = VerificationFile.model_validate_json(json.dumps(data), strict=True)
    if result.run_id != path.parent.name or result.product != case.product:
        raise ValueError("contexto da verificação divergente")
    return result


def _judgment(truth: str, prediction: bool | None) -> str:
    if prediction is None or truth == "indeterminado":
        return "indeterminado"
    return "acertou" if prediction == (truth == "real") else "errou"


def _reason(error: Exception) -> str:
    if type(error) is ValueError:
        return str(error)
    return type(error).__name__


def _measure_run(
    folder: Path, case: Case, mode: str
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    try:
        findings = _report(folder / "findings.json", case)
    except (OSError, UnicodeError, ValueError, TypeError, ValidationError) as error:
        return [], [{"run_id": folder.name, "arquivo": "findings.json", "motivo": _reason(error)}]
    triage: TriageFile | None = None
    verification: VerificationFile | None = None
    declared: set[str] = set()
    for name in ("triage", "verification"):
        try:
            if name == "triage":
                triage, declared = _load_triage(folder / "triage.json")
            else:
                verification = _load_verification(folder / "verification.json", case)
        except (OSError, UnicodeError, ValueError, TypeError, ValidationError) as error:
            issues.append(
                {"run_id": folder.name, "arquivo": name + ".json", "motivo": _reason(error)}
            )
    known = {item["fingerprint"] for item in findings}
    annotations = {x.fingerprint: x for x in triage.annotations} if triage else {}
    entries = {x.fingerprint: x for x in verification.entries} if verification else {}
    for name, values in (("triage.json", annotations), ("verification.json", entries)):
        for fingerprint in sorted(values.keys() - known):
            issues.append(
                {
                    "run_id": folder.name,
                    "arquivo": name,
                    "motivo": "fingerprint órfão: " + fingerprint,
                }
            )
    rows = []
    for finding in findings:
        fingerprint = finding["fingerprint"]
        flaw_id, truth, reason = _truth(case, mode, finding)
        technique = finding.get("technique")
        kind = str(
            finding.get("category")
            or (technique if technique and technique != "zap_active_scan" else finding["title"])
        )
        entry = entries.get(fingerprint)
        annotation = annotations.get(fingerprint) if fingerprint in declared else None
        level = entry.level if entry else None
        prediction = (
            True
            if level in ("reproduced", "likely")
            else False
            if level == "likely_false_positive"
            else None
        )
        rows.append(
            {
                "run_id": folder.name,
                "fingerprint": fingerprint,
                "tipo": kind,
                "falha": flaw_id,
                "verdade": truth,
                "motivo": reason,
                "nivel": level,
                "cli": _judgment(truth, prediction) if entry else "não avaliado",
                "motivo_cli": (
                    "sem resultado para este fingerprint"
                    if entry is None
                    else "nível inconclusivo ou não verificável"
                    if prediction is None
                    else reason
                ),
                "motivo_agente": (
                    "sem classificação explícita para este fingerprint"
                    if annotation is None
                    else reason
                ),
                "suspected_false_positive": annotation.suspected_false_positive
                if annotation
                else None,
                "agente": _judgment(truth, not annotation.suspected_false_positive)
                if annotation
                else "não avaliado",
            }
        )
    return rows, issues


def measure(trace: Path, case: Case, mode: str) -> dict[str, Any]:
    """Mede sem alterar a nota histórica; falhas de leitura nunca viram acertos."""
    runs = trace / "runs"
    folders = sorted(p for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    if not folders:
        issues.append({"run_id": "", "arquivo": "runs", "motivo": "nenhuma execução encontrada"})
    for folder in folders:
        measured, problems = _measure_run(folder, case, mode)
        rows.extend(measured)
        issues.extend(problems)
    matrix = {}
    for kind in sorted({row["tipo"] for row in rows}):
        selected = [row for row in rows if row["tipo"] == kind]
        cli = Counter((row["verdade"], row["nivel"]) for row in selected)
        matrix[kind] = {
            "reais_reproduzidos": cli[("real", "reproduced")],
            "falsos_reproduzidos": cli[("false", "reproduced")],
            "falsos_classificados_fp": cli[("false", "likely_false_positive")],
            "reais_classificados_fp": cli[("real", "likely_false_positive")],
            "denominador": len(selected),
            "cli": dict(Counter(row["cli"] for row in selected)),
            "agente": dict(Counter(row["agente"] for row in selected)),
            "agente_falsos_marcados_fp": sum(
                row["verdade"] == "false" and row["suspected_false_positive"] is True
                for row in selected
            ),
            "agente_reais_marcados_fp": sum(
                row["verdade"] == "real" and row["suspected_false_positive"] is True
                for row in selected
            ),
        }
    return {"schema_version": 1, "observacoes": rows, "matriz": matrix, "problemas": issues}
