"""Sinais de erro interno vistos pela cerca (ADR 0049) contra a Clínica Piloto, nos dois modos.

Nível RÁPIDO: uma pilha por modo, COM `stack up --build` (obrigatório: sem ele a cerca é a
antiga e o teste mediria a imagem velha), `probe`, `scan` de uma operação de leitura e `report`.
Prova o CONTRATO, não a sorte do ZAP: o pedido que provoca o erro sai do próprio `probe`. A CÓPIA
descartável do `data-rules.yml` ganha uma regra que fixa `nome` de `buscarPacientesPorNome` numa
aspa simples (o valor que o `probe` observou como o que derruba a busca no modo vulnerável), então
o sinal não depende de o varredor provocar o erro e nenhum pedido sai por fora dos comandos `hdast`.

No modo vulnerável o alvo devolve 500 com detalhes internos no corpo. O texto exato da pilha não é
fixado aqui: o teste procura, na trilha do proxy, na auditoria da CLI e nos artefatos do sinal
(`error-signals.json`, `findings.json`, `report.md`, `report.html`), qualquer trecho conhecido da
pilha e exige zero ocorrência. O `probe.json` guarda o trecho curto e neutralizado da resposta de
erro (`untrusted_target_data`, comportamento anterior ao ADR 0049) e por isso fica fora dessa
checagem. A duração por requisição da auditoria é GRAVADA em
`HDAST_IT_METRICS_DIR/lab-error-signals-<modo>.json` e não vira asserção.

O que a prova não cobre: o conteúdo real de um produto, respostas em `br` ou `zstd` e HTTPS de
um ambiente corporativo (só HTTP no laboratório).
"""

import json
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

from tests.integration.lab_support import PILOT_PROFILE, LabCli, proxy_audit, require_docker
from tests.integration.run_support import record_metrics, throwaway_pilot_env

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

MODES = ("vulnerable", "secure")
SEARCH_OPERATION = "buscarPacientesPorNome"
SEARCH_PATH = "/api/pacientes/busca"
BREAKING_RULE = """  - match: { operation: buscarPacientesPorNome, field: nome }
    generator: constant
    args: { value: "'" }
"""
# Artefatos de sinal e de relatório (o `probe.json` fica de fora: ver o docstring do módulo).
SIGNAL_ARTIFACTS = ("error-signals.json", "findings.json", "audit.jsonl")
# O alerta do ZAP guarda a evidência da própria varredura (ADR 0022, anterior ao 0049), redigida
# e cortada: é outro canal, que o ADR 0049 não altera. Registrado nas medidas, fora da asserção.
ZAP_EVIDENCE = "/evidence/"
REPORT_FILES = ("report.md", "report.html")
# Pedaços de uma pilha de chamadas Java que NÃO podem aparecer em nenhum arquivo gravado.
STACK_FRAGMENTS = ("\tat dev.hdast", "at dev.hdast.pilot", "org.springframework.", "java.sql.")


@dataclass
class SignalsLab:
    """O que foi medido em um modo, coletado enquanto a pilha dele estava no ar."""

    mode: str
    run_id: str
    proxy_rows: list[dict[str, Any]]
    findings: dict[str, Any]
    error_signals: dict[str, Any]
    leaked: list[str]
    zap_evidence: list[str]
    reports_with_fragments: list[str]
    probe_outcome: str
    probe_seconds: float
    scan_summary: dict[str, Any]

    def released_with_status(self) -> list[dict[str, Any]]:
        """Linhas liberadas com status dentro da janela do relatório."""
        window = self.findings["proxy_signals"]["window"]
        start = datetime.fromisoformat(window["start"])
        end = datetime.fromisoformat(window["end"])
        return [
            row
            for row in self.proxy_rows
            if row["decision"] == "allow"
            and row.get("status") is not None
            and start <= datetime.fromisoformat(row["ts"]) <= end
        ]


def _json_paths_with_fragments(node: object, trail: str = "") -> list[str]:
    """Caminhos (sem o texto) dos valores de um JSON que contêm trecho de pilha de chamadas."""
    if isinstance(node, dict):
        return [
            hit for k, v in node.items() for hit in _json_paths_with_fragments(v, f"{trail}/{k}")
        ]
    if isinstance(node, list):
        return [
            hit
            for i, v in enumerate(node)
            for hit in _json_paths_with_fragments(v, f"{trail}[{i}]")
        ]
    if isinstance(node, str) and any(f in node for f in STACK_FRAGMENTS):
        return [trail]
    return []


def _leaks(cli: LabCli) -> tuple[list[str], list[str], list[str]]:
    """Onde há trecho da pilha: (canal do sinal, evidência do ZAP, arquivos de relatório)."""
    leaks: list[str] = []
    zap_evidence: list[str] = []
    paths = [p for p in cli.runs.rglob("*") if p.name in SIGNAL_ARTIFACTS]
    paths += [p for p in (cli.state / "stacks").rglob("*") if p.name == "audit.jsonl"]
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        name = str(path.relative_to(cli.root))
        if path.suffix == ".json":
            for where in _json_paths_with_fragments(json.loads(text)):
                (zap_evidence if ZAP_EVIDENCE in where else leaks).append(f"{name}:{where}")
        elif any(fragment in text for fragment in STACK_FRAGMENTS):
            leaks.append(name)
    reports = [
        str(p.relative_to(cli.root))
        for p in cli.runs.rglob("*")
        if p.name in REPORT_FILES
        and any(f in p.read_text(encoding="utf-8", errors="replace") for f in STACK_FRAGMENTS)
    ]
    return leaks, zap_evidence, reports


def _measure(cli: LabCli, mode: str) -> SignalsLab:
    flags = ["--secure"] if mode == "secure" else []
    up = cli.run("stack", "up", "clinica-piloto", "--build", *flags, timeout=900)
    assert up.code == 0, up.stdout[-500:]
    assert cli.run("preflight", "clinica-piloto").code == 0
    started = time.monotonic()
    probe = cli.run("probe", "clinica-piloto", timeout=900)
    probe_seconds = round(time.monotonic() - started, 1)
    assert probe.code == 0, probe.stdout[-500:]
    run_id = str(probe.envelope["run_id"])
    scan = cli.run(
        "scan", "clinica-piloto", "--run", run_id, "--only", SEARCH_OPERATION,
        "--max-minutes", "3", timeout=900,
    )  # fmt: skip
    assert scan.code in {0, 3}, scan.stdout[-500:]
    scan_file = json.loads((cli.runs / run_id / "scan.json").read_text(encoding="utf-8"))
    scan_summary = {
        "exit_code": scan.code,
        "status": scan_file["status"],
        "entries": len(scan_file["entries"]),
        "skipped": [s["reason"] for s in scan_file["skipped"]],
    }
    assert cli.run("report", "clinica-piloto", "--run", run_id).code in {0, 1}
    directory = cli.runs / run_id
    findings = json.loads((directory / "findings.json").read_text(encoding="utf-8"))
    signals_file = json.loads((directory / "error-signals.json").read_text(encoding="utf-8"))
    probe_file = json.loads((directory / "probe.json").read_text(encoding="utf-8"))
    outcomes = [
        r["outcome"] for r in probe_file["operations"] if r["operation_id"] == SEARCH_OPERATION
    ]
    leaked, zap_evidence, reports = _leaks(cli)
    return SignalsLab(
        mode=mode,
        run_id=run_id,
        proxy_rows=proxy_audit(cli),
        findings=findings,
        error_signals=signals_file,
        leaked=leaked,
        zap_evidence=zap_evidence,
        reports_with_fragments=reports,
        probe_outcome=outcomes[0] if outcomes else "absent",
        probe_seconds=probe_seconds,
        scan_summary=scan_summary,
    )


def _duration_stats(released: list[dict[str, Any]]) -> dict[str, Any]:
    """Duração por resposta (ms), com o corte entre respostas lidas e puladas pela cerca."""

    def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        values = sorted(r["duration_ms"] for r in rows if r.get("duration_ms") is not None)
        if not values:
            return {"n": 0}
        return {
            "n": len(values),
            "mean": round(sum(values) / len(values), 2),
            "p95": values[min(len(values) - 1, int(len(values) * 0.95))],
            "max": values[-1],
        }

    read = [r for r in released if r.get("signal_skip") is None]
    return {
        "all": stats(released),
        "read_by_the_fence": stats(read),
        "not_read": stats([r for r in released if r.get("signal_skip") is not None]),
        "read_with_signal": stats([r for r in read if r.get("signals")]),
    }


def _observations(lab: SignalsLab) -> dict[str, Any]:
    released = lab.released_with_status()
    durations = [row["duration_ms"] for row in released if row.get("duration_ms") is not None]
    return {
        "mode": lab.mode,
        "released_with_status": len(released),
        "mean_duration_ms": round(sum(durations) / len(durations), 2) if durations else None,
        "rows_with_signals": sum(1 for row in released if row.get("signals")),
        "categories": dict(Counter(c for row in released for c in row.get("signals", []))),
        "skipped": dict(Counter(row.get("signal_skip") for row in released)),
        "probe_outcome_of_the_search": lab.probe_outcome,
        "probe_seconds": lab.probe_seconds,
        "fragments_in_zap_evidence_of_findings_json": lab.zap_evidence,
        "report_files_with_fragments_from_zap_evidence": lab.reports_with_fragments,
        "search_rows_by_status": dict(
            Counter(str(row["status"]) for row in released if row["path"] == SEARCH_PATH)
        ),
        "search_rows_with_signals": [
            {k: row.get(k) for k in ("status", "bytes", "duration_ms", "signals")}
            for row in released
            if row["path"] == SEARCH_PATH and row.get("signals")
        ],
        "scan": lab.scan_summary,
        "duration_ms": _duration_stats(released),
        "proxy_signals": lab.findings["proxy_signals"],
    }


@pytest.fixture(scope="module", params=MODES)
def lab(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[SignalsLab]:
    require_docker()
    mode = str(request.param)
    cli = LabCli(tmp_path_factory.mktemp(f"signals-{mode}"), throwaway_pilot_env())
    installed = cli.install_product("clinica-piloto", PILOT_PROFILE)
    rules = installed / "data-rules.yml"
    rules.write_text(rules.read_text(encoding="utf-8") + BREAKING_RULE, encoding="utf-8")
    try:
        measured = _measure(cli, mode)
        record_metrics(f"lab-error-signals-{mode}", _observations(measured))
        yield measured
    finally:
        cli.stack_down()


def test_error_signals_json_exists_and_findings_carry_a_coherent_proxy_signals(
    lab: SignalsLab,
) -> None:
    signals = lab.findings["proxy_signals"]
    assert signals["enabled"] is True
    assert lab.error_signals == signals
    assert sum(signals["counts"].values()) >= signals["responses_with_signal"]
    assert signals["findings"] or signals["responses_with_signal"] == 0


def test_examined_plus_skipped_equals_the_released_rows_with_status_in_the_window(
    lab: SignalsLab,
) -> None:
    signals = lab.findings["proxy_signals"]
    total = signals["responses_examined"] + sum(signals["responses_skipped"].values())
    assert total == len(lab.released_with_status())
    assert total > 0


def test_signal_counts_match_the_audit_rows_of_the_window(lab: SignalsLab) -> None:
    signals = lab.findings["proxy_signals"]
    expected: Counter[str] = Counter()
    for row in lab.released_with_status():
        for category in row.get("signals", []):
            expected[category] += 1
    assert {k: v for k, v in signals["counts"].items() if v} == dict(expected)


def test_in_vulnerable_mode_the_fence_counts_a_java_stack_trace_and_in_secure_mode_it_does_not(
    lab: SignalsLab,
) -> None:
    rows = [r for r in lab.released_with_status() if r["path"] == SEARCH_PATH]
    categories = {c for row in lab.released_with_status() for c in row.get("signals", [])}
    if lab.mode == "vulnerable":
        assert lab.probe_outcome == "server_error"
        assert any(row["status"] >= 500 for row in rows)
        assert "stack_trace_java" in categories
        assert lab.findings["proxy_signals"]["counts"]["stack_trace_java"] >= 1
        assert any(
            f["category"] == "stack_trace_java" for f in lab.findings["proxy_signals"]["findings"]
        )
    else:
        assert "stack_trace_java" not in categories
        assert lab.findings["proxy_signals"]["counts"].get("stack_trace_java", 0) == 0


def test_no_audit_line_and_no_file_of_the_run_contains_response_text(lab: SignalsLab) -> None:
    assert lab.leaked == []
    for row in lab.proxy_rows:
        assert set(row) <= {
            "ts", "run_id", "method", "scheme", "host", "port", "path", "query_params",
            "decision", "reason", "detail", "status", "bytes", "duration_ms", "waited_ms",
            "signals", "signal_skip",
        }  # fmt: skip


def test_plain_json_200_responses_have_no_signals(lab: SignalsLab) -> None:
    plain = [
        row
        for row in lab.released_with_status()
        if row["status"] == 200 and row.get("signal_skip") is None
    ]
    assert plain
    assert [row for row in plain if row.get("signals")] == []


def test_sinais_agrupam_por_operacao_e_categoria(lab: SignalsLab) -> None:
    findings = lab.findings["proxy_signals"]["findings"]
    keys = [(f["category"], f["method"], f["operation_id"]) for f in findings]
    assert len(keys) == len(set(keys))
    assert lab.findings["proxy_signals"]["findings_omitted"] == 0
    if lab.mode == "vulnerable":
        assert any(f["operation_id"] == SEARCH_OPERATION for f in findings)
