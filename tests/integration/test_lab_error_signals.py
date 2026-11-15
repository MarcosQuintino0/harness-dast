"""Sinais de erro interno vistos pela cerca (ADR 0049) contra a Clínica Piloto, nos dois modos.

Nível RÁPIDO: uma pilha por modo, COM `stack up --build` (obrigatório: sem ele a cerca é a
antiga e o teste mediria a imagem velha), `probe`, `scan` de uma operação de leitura e `report`.
Prova o CONTRATO, não a sorte do ZAP: o pedido que quebra a busca no modo vulnerável é enviado
pelo proxy publicado (`via_proxy`), então o sinal não depende de o varredor provocar o erro.

O pedido que quebra a busca é uma aspa simples em `nome` de `/api/pacientes/busca`; no modo
vulnerável o piloto devolve o rastreamento de exceção no corpo de respostas 500. O texto exato
da pilha não é fixado aqui: o teste procura na pasta das execuções e na trilha do proxy qualquer
trecho conhecido da pilha e exige zero ocorrência. A duração média por requisição da auditoria é
GRAVADA em `HDAST_IT_METRICS_DIR/lab-error-signals-<modo>.json` e não vira asserção.

O que a prova não cobre: o conteúdo real de um produto, respostas em `br` ou `zstd` e HTTPS de
um ambiente corporativo (só HTTP no laboratório).
"""

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

from tests.integration.lab_support import PILOT_PROFILE, LabCli, proxy_audit, require_docker
from tests.integration.path_support import pilot_token, via_proxy
from tests.integration.run_support import record_metrics, throwaway_pilot_env

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

MODES = ("vulnerable", "secure")
BREAKING_SEARCH = "/api/pacientes/busca?nome=%27"
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
    breaking_status: int

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


def _leaks(cli: LabCli) -> list[str]:
    """Arquivos (execuções e trilha do proxy) que contêm trecho conhecido da pilha de chamadas."""
    roots = [cli.runs, cli.state / "stacks"]
    found: list[str] = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(fragment in text for fragment in STACK_FRAGMENTS):
                found.append(str(path.relative_to(cli.root)))
    return found


def _measure(cli: LabCli, mode: str) -> SignalsLab:
    flags = ["--secure"] if mode == "secure" else []
    up = cli.run("stack", "up", "clinica-piloto", "--build", *flags, timeout=900)
    assert up.code == 0, up.stdout[-500:]
    assert cli.run("preflight", "clinica-piloto").code == 0
    probe = cli.run("probe", "clinica-piloto", timeout=900)
    assert probe.code == 0, probe.stdout[-500:]
    run_id = str(probe.envelope["run_id"])
    scan = cli.run(
        "scan", "clinica-piloto", "--run", run_id, "--only", "buscarPacientesPorNome",
        "--max-minutes", "3", timeout=900,
    )  # fmt: skip
    assert scan.code in {0, 3}, scan.stdout[-500:]
    breaking = via_proxy(BREAKING_SEARCH, token=pilot_token(throwaway_pilot_env_of(cli)))
    assert cli.run("report", "clinica-piloto", "--run", run_id).code in {0, 1}
    directory = cli.runs / run_id
    findings = json.loads((directory / "findings.json").read_text(encoding="utf-8"))
    signals_file = json.loads((directory / "error-signals.json").read_text(encoding="utf-8"))
    return SignalsLab(
        mode=mode,
        run_id=run_id,
        proxy_rows=proxy_audit(cli),
        findings=findings,
        error_signals=signals_file,
        leaked=_leaks(cli),
        breaking_status=breaking.status,
    )


def throwaway_pilot_env_of(cli: LabCli) -> dict[str, str]:
    """Credenciais descartáveis do piloto que esta sessão do `LabCli` usa (só do laboratório)."""
    return {name: value for name, value in cli.env.items() if name.startswith("PILOT_")}


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
        "breaking_search_status": lab.breaking_status,
        "proxy_signals": lab.findings["proxy_signals"],
    }


@pytest.fixture(scope="module", params=MODES)
def lab(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[SignalsLab]:
    require_docker()
    mode = str(request.param)
    cli = LabCli(tmp_path_factory.mktemp(f"signals-{mode}"), throwaway_pilot_env())
    cli.install_product("clinica-piloto", PILOT_PROFILE)
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


def test_in_vulnerable_mode_a_released_row_carries_a_java_stack_trace_and_in_secure_none_does(
    lab: SignalsLab,
) -> None:
    categories = {c for row in lab.released_with_status() for c in row.get("signals", [])}
    if lab.mode == "vulnerable":
        assert lab.breaking_status >= 500
        assert "stack_trace_java" in categories
    else:
        assert "stack_trace_java" not in categories


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
