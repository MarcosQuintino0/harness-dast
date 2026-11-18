"""Varrer as operações que deram "não encontrado" (ADR 0050) na Clínica Piloto, nos dois modos.

Nível RÁPIDO: uma pilha por modo, COM `stack up --build`, `preflight` e um `probe` completo. A
operação que o teste varre é ESCOLHIDA pelo que o `probe` mostrou (a primeira de leitura com
resultado `not_found` em `probe.json`), nunca por uma lista fixa. Para o `probe` dar 404, a CÓPIA
descartável do `data-rules.yml` aponta um parâmetro de caminho para um registro que não existe.
Sem o campo `scan.include_outcomes` no perfil, o plano deixa a operação de fora, com o motivo
`not_success`. Com
`scan.include_outcomes: [not_found]` (acrescentado só na CÓPIA descartável do perfil, no papel da
carta), o plano a inclui com `seed_outcome: not_found` e o `scan` de verdade a varre: a entrada
do `scan.json` leva a mesma classe, o ZAP envia pedidos pela cerca, que libera os de método e
caminho permitidos e recusa, com motivo, as variações de caminho
fora do modelo (as recusas são contadas, não proibidas).

O que vira medida e não asserção: quantas operações deram `not_found` no `probe`, o tempo da
varredura, os alertas. Vão para `HDAST_IT_METRICS_DIR/lab-include-outcomes-<modo>.json`.

O que a prova não cobre: as outras classes (`validation_error`, `conflict`...), a flag
`--include-outcome` combinada com o perfil e produto real.
"""

import json
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tests.integration.lab_support import PILOT_PROFILE, LabCli, proxy_audit, require_docker
from tests.integration.run_support import record_metrics, throwaway_pilot_env

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

MODES = ("vulnerable", "secure")
# Com os dados do perfil o `probe` alcança todas as leituras (nenhuma dá 404): os valores fixos de
# caminho são de registros da semente. Na CÓPIA descartável do `data-rules.yml` dois deles passam a
# ser de registros que não existem. O que conta é o que o `probe` observar: o teste escolhe a
# operação em `probe.json`, não nestas trocas.
MISSING_RECORDS = (
    ("value: laudo-0001.txt", "value: nao-existe.txt"),
    ('value: "00000001"', 'value: "77777777"'),
)
INCLUDE_FLAG = "\nscan:\n  include_outcomes: [not_found]\n"
OUTCOME = "not_found"


@dataclass
class OutcomesLab:
    """O que foi medido em um modo, coletado enquanto a pilha dele estava no ar."""

    mode: str
    run_id: str
    operation: str
    path_template: str
    outcomes_in_probe: dict[str, int]
    not_found_operations: list[str]
    without_field: dict[str, Any]
    with_field: dict[str, Any]
    live_exit: int
    live: dict[str, Any]
    proxy_rows: list[dict[str, Any]]
    scan_proxy_rows: list[dict[str, Any]]
    seconds: dict[str, float] = field(default_factory=dict)

    def planned(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Entradas do plano da operação escolhida."""
        return [p for p in data["planned"] if p["operation_id"] == self.operation]

    def skipped(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Entradas de operação não varrida da operação escolhida."""
        return [s for s in data["skipped"] if s["operation_id"] == self.operation]


def _enable_include_outcomes(profile_file: Path) -> None:
    """Liga o campo só na CÓPIA descartável (faz o papel da carta)."""
    text = profile_file.read_text(encoding="utf-8")
    assert "\nscan:" not in text
    profile_file.write_text(text.rstrip("\n") + "\n" + INCLUDE_FLAG, encoding="utf-8", newline="\n")


def _pick_operation(probe_file: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Primeira operação de leitura que o `probe` classificou como `not_found`."""
    found = [r for r in probe_file["operations"] if r["outcome"] == OUTCOME]
    names = [str(r["operation_id"]) for r in found]
    reads = [r for r in found if r["method"] == "GET"]
    assert reads, f"o probe não deixou nenhuma leitura como {OUTCOME}: {names}"
    chosen = reads[0]
    return str(chosen["operation_id"]), str(chosen["path"]), names


def _probe_after_restack(
    cli: LabCli, flags: list[str], operation: str, seconds: dict[str, float]
) -> tuple[str, dict[str, Any]]:
    """Sobe a pilha de novo (ADR 0081), refaz o `probe` e devolve o `run_id` novo."""
    started = time.monotonic()
    up = cli.restack("clinica-piloto", "--build", *flags)
    assert up.code == 0, (up.stdout + up.stderr)[-1200:]
    seconds["restack"] = round(time.monotonic() - started, 1)
    preflight = cli.run("preflight", "clinica-piloto")
    assert preflight.code == 0, (preflight.stdout + preflight.stderr)[-1200:]
    started = time.monotonic()
    probe = cli.run("probe", "clinica-piloto", timeout=900)
    seconds["probe_with_field"] = round(time.monotonic() - started, 1)
    assert probe.code == 0, (probe.stdout + probe.stderr)[-1200:]
    run_id = str(probe.envelope["run_id"])
    probe_file = json.loads((cli.runs / run_id / "probe.json").read_text(encoding="utf-8"))
    again = [r["outcome"] for r in probe_file["operations"] if r["operation_id"] == operation]
    assert again == [OUTCOME], (
        f"Depois de subir a pilha de novo, a operação {operation} deu {again} no probe "
        f"{run_id}, e não [{OUTCOME!r}]."
    )
    return run_id, probe_file


def _measure(cli: LabCli, mode: str) -> OutcomesLab:
    seconds: dict[str, float] = {}
    flags = ["--secure"] if mode == "secure" else []
    started = time.monotonic()
    up = cli.run("stack", "up", "clinica-piloto", "--build", *flags, timeout=900)
    assert up.code == 0, up.stdout[-500:]
    seconds["stack_up_build"] = round(time.monotonic() - started, 1)
    assert cli.run("preflight", "clinica-piloto").code == 0
    started = time.monotonic()
    probe = cli.run("probe", "clinica-piloto", timeout=900)
    seconds["probe"] = round(time.monotonic() - started, 1)
    assert probe.code == 0, probe.stdout[-800:]
    run_id = str(probe.envelope["run_id"])
    probe_file = json.loads((cli.runs / run_id / "probe.json").read_text(encoding="utf-8"))
    operation, path_template, not_found = _pick_operation(probe_file)
    base = ["scan", "clinica-piloto", "--run", run_id, "--only", operation]
    without = cli.run(*base, "--dry-run")
    assert without.code == 0, without.stdout[-800:]
    _enable_include_outcomes(cli.products / "clinica-piloto" / "target.yml")
    run_id, probe_file = _probe_after_restack(cli, flags, operation, seconds)
    base = ["scan", "clinica-piloto", "--run", run_id, "--only", operation]
    with_field = cli.run(*base, "--dry-run")
    assert with_field.code == 0, with_field.stdout[-800:]
    # Só as linhas que o scan acrescentou: o probe novo também passa pela cerca na mesma pilha.
    proxy_before = len(proxy_audit(cli))
    started = time.monotonic()
    live = cli.run(*base, "--max-minutes", "5", timeout=900)
    seconds["scan"] = round(time.monotonic() - started, 1)
    scan_file = cli.runs / run_id / "scan.json"
    output = (live.stdout + live.stderr)[-1200:]
    assert live.code in {0, 3}, f"O scan terminou com código {live.code}.\n{output}"
    assert scan_file.is_file(), f"O scan não gerou {scan_file}.\n{output}"
    all_rows = proxy_audit(cli)
    return OutcomesLab(
        mode=mode,
        run_id=run_id,
        operation=operation,
        path_template=path_template,
        outcomes_in_probe=dict(Counter(r["outcome"] for r in probe_file["operations"])),
        not_found_operations=not_found,
        without_field=without.data,
        with_field=with_field.data,
        live_exit=live.code,
        live=json.loads(scan_file.read_text(encoding="utf-8")),
        proxy_rows=all_rows,
        scan_proxy_rows=all_rows[proxy_before:],
        seconds=seconds,
    )


def _observations(lab: OutcomesLab) -> dict[str, Any]:
    entry = [e for e in lab.live["entries"] if e["operation_id"] == lab.operation]
    rows = [r for r in lab.scan_proxy_rows if r["path"].startswith(lab.path_template.split("{")[0])]
    return {
        "mode": lab.mode,
        "seconds": lab.seconds,
        "probe_outcomes": lab.outcomes_in_probe,
        "not_found_operations": lab.not_found_operations,
        "chosen_operation": lab.operation,
        "dry_run_without_field": {
            "planned": lab.planned(lab.without_field),
            "skipped": lab.skipped(lab.without_field),
            "include_outcomes": lab.without_field["include_outcomes"],
        },
        "dry_run_with_field": {
            "planned": lab.planned(lab.with_field),
            "skipped": lab.skipped(lab.with_field),
            "include_outcomes": lab.with_field["include_outcomes"],
        },
        "live_exit": lab.live_exit,
        "live_status": lab.live["status"],
        "live_entries": entry,
        "live_alerts_total": lab.live.get("alerts_total"),
        "proxy_rows_for_the_path": dict(Counter(f"{r['method']} {r['decision']}" for r in rows)),
        "proxy_deny_reasons_for_the_path": dict(
            Counter(r["reason"] for r in rows if r["decision"] == "deny")
        ),
    }


@pytest.fixture(scope="module", params=MODES)
def lab(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[OutcomesLab]:
    require_docker()
    mode = str(request.param)
    cli = LabCli(tmp_path_factory.mktemp(f"outcomes-{mode}"), throwaway_pilot_env())
    installed = cli.install_product("clinica-piloto", PILOT_PROFILE)
    rules = installed / "data-rules.yml"
    text = rules.read_text(encoding="utf-8")
    for seeded, missing in MISSING_RECORDS:
        assert seeded in text, "o perfil do piloto deixou de fixar um valor de caminho da semente"
        text = text.replace(seeded, missing)
    rules.write_text(text, encoding="utf-8")
    try:
        measured = _measure(cli, mode)
        record_metrics(f"lab-include-outcomes-{mode}", _observations(measured))
        yield measured
    finally:
        cli.stack_down()


def test_without_the_field_the_not_found_operation_stays_out_of_the_plan(lab: OutcomesLab) -> None:
    assert lab.without_field["include_outcomes"] == []
    assert lab.planned(lab.without_field) == []
    skipped = lab.skipped(lab.without_field)
    assert [s["reason"] for s in skipped] == ["not_success"]


def test_with_the_field_the_operation_enters_the_plan_with_the_seed_outcome(
    lab: OutcomesLab,
) -> None:
    assert lab.with_field["include_outcomes"] == [OUTCOME]
    planned = lab.planned(lab.with_field)
    assert [p["seed_outcome"] for p in planned] == [OUTCOME]
    assert lab.skipped(lab.with_field) == []


def test_the_live_scan_attacks_the_operation_and_records_the_seed_outcome(
    lab: OutcomesLab,
) -> None:
    assert lab.live_exit in {0, 3}
    assert lab.live["include_outcomes"] == [OUTCOME]
    entries = [e for e in lab.live["entries"] if e["operation_id"] == lab.operation]
    assert len(entries) == 1
    assert entries[0]["seed_outcome"] == OUTCOME


def test_every_proxy_row_of_the_scan_was_decided_by_the_fence_and_none_was_a_delete(
    lab: OutcomesLab,
) -> None:
    prefix = lab.path_template.split("{")[0]
    rows = [r for r in lab.scan_proxy_rows if r["path"].startswith(prefix)]
    assert rows
    assert {r["decision"] for r in rows} <= {"allow", "deny"}
    assert any(r["decision"] == "allow" for r in rows)
    # O ZAP também manda variações de caminho que a cerca recusa: a recusa é o que se espera,
    # desde que venha com motivo e que nada fora do escopo tenha sido liberado.
    assert all(r.get("reason") for r in rows if r["decision"] == "deny")
    allowed_methods = {r["method"] for r in rows if r["decision"] == "allow"}
    assert allowed_methods <= {"GET", "POST", "PUT", "PATCH"}
    assert "DELETE" not in {r["method"] for r in lab.proxy_rows}
