"""Valores que o esquema proíbe (`hdast negative`, ADR 0051) na Clínica Piloto, nos dois modos.

Nível RÁPIDO: uma pilha por modo, COM `stack up --build`, `preflight` e um `probe` completo. Depois,
`hdast negative --run <id>` em duas rodadas sobre o mesmo `probe`:

1. leitura (padrão do perfil: `negative.allow_writes` ausente), só `GET`;
2. escrita, com `negative.allow_writes: true` acrescentado só na CÓPIA descartável do perfil (no
   laboratório isso faz o papel da carta de autorização; o perfil versionado não é alterado).

Entre as duas, `hdast run --skip-scan` com e sem `--no-negative`, olhando o estágio no `run.json`.

Prova o CONTRATO do estágio, não o gabarito: nenhum `DELETE` sai; todo pedido do estágio passa pela
cerca (decisão `allowed` na CLI e `allow` no proxy); o valor inválido nunca vira texto em artefato
nem na auditoria do proxy (que guarda só os NOMES dos parâmetros de consulta); toda escrita aceita
ou com erro 5xx tem a restauração registrada; o `negative.json` é coerente consigo mesmo e com a
trilha. As contagens por classe, os 4xx, 2xx e 5xx, os achados e os tempos são GRAVADOS em
`HDAST_IT_METRICS_DIR/lab-negative-<modo>.json` e não viram asserção: quem interpreta é a pessoa que
lê a evidência.

O que a prova não cobre: o resultado de cada classe em cada modo (isso é medida), valores válidos
que o OpenAPI não modela (`pattern`, formato), corpo de formulário e `multipart` e produto real.
"""

import json
import re
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.integration.lab_support import (
    PILOT_PROFILE,
    LabCli,
    proxy_audit,
    require_docker,
    run_audit,
)
from tests.integration.run_support import (
    ZapHistory,
    files_containing,
    record_metrics,
    secret_values,
    throwaway_pilot_env,
)

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

PILOT_BASE = "http://clinica-piloto:8080"
MODES = ("vulnerable", "secure")
WRITES_FLAG = "\nnegative:\n  allow_writes: true\n"
# Valores fixos que o domínio manda (`domain/negative_values.py`) e a corrida de `a` do `too_long`:
# nenhum pode aparecer em artefato nem na auditoria do proxy.
INVALID_NEEDLES = ("not-a-number", "not-a-boolean", "not-in-enum")
LONG_RUN = re.compile(r"a{30,}")
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH"})


@dataclass
class Round:
    """O que uma rodada do `negative` deixou: resultado, trilhas e tempo."""

    name: str
    exit_code: int
    seconds: float
    result: dict[str, Any]
    cli_rows: list[dict[str, Any]]
    proxy_rows: list[dict[str, Any]]

    def sent(self) -> list[dict[str, Any]]:
        """Linhas `result` da CLI que pertencem ao estágio (inclui restaurações)."""
        return [
            r
            for r in self.cli_rows
            if r["phase"] == "result" and str(r["operation_id"]).startswith("negative:")
        ]

    def decisions(self) -> list[dict[str, Any]]:
        """Linhas `decision` da CLI que pertencem ao estágio."""
        return [
            r
            for r in self.cli_rows
            if r["phase"] == "decision" and str(r["operation_id"]).startswith("negative:")
        ]

    def restores(self) -> list[dict[str, Any]]:
        """Restaurações (`negative:restore:...`) enviadas."""
        return [r for r in self.sent() if str(r["operation_id"]).startswith("negative:restore:")]


@dataclass
class NegativeLab:
    """O que foi medido em um modo, coletado enquanto a pilha dele estava no ar."""

    mode: str
    probe_run_id: str
    write_probe_run_id: str = ""
    rounds: dict[str, Round] = field(default_factory=dict)
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    leaked_files: list[str] = field(default_factory=list)
    leaked_proxy: list[str] = field(default_factory=list)
    secret_hits: list[str] = field(default_factory=list)
    seconds: dict[str, float] = field(default_factory=dict)


def _same_audit_request(
    proxy_row: dict[str, Any], decision: dict[str, Any], result: dict[str, Any]
) -> bool:
    fields = ("method", "scheme", "host", "port", "path")
    same_destination = all(
        key in proxy_row
        and proxy_row[key] not in (None, "")
        and proxy_row[key] == decision.get(key) == result.get(key)
        for key in fields
    )
    query_names = proxy_row.get("query_params")
    return (
        same_destination
        and isinstance(query_names, list)
        and query_names == decision.get("query_names") == result.get("query_names")
    )


def _inside_audit_interval(
    row: dict[str, Any], decision: dict[str, Any], result: dict[str, Any]
) -> bool:
    try:
        instant = datetime.fromisoformat(row["ts"])
        start = datetime.fromisoformat(decision["timestamp"])
        end = datetime.fromisoformat(result["timestamp"])
        if any(value.utcoffset() is None for value in (instant, start, end)):
            return False
        # O proxy grava milissegundos; a CLI grava microssegundos.
        margin = timedelta(milliseconds=1)
        return start - margin <= instant <= end + margin
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _correlated_backoff(
    row: dict[str, Any],
    decisions: dict[int, dict[str, Any]],
    results: list[dict[str, Any]],
    used: set[int],
) -> int | None:
    """Associa uma única recusa operacional à tentativa auditada pela CLI."""
    if (
        row.get("decision") != "deny"
        or row.get("reason") != "rate_backoff"
        or row.get("status") != 429
    ):
        return None
    for result in results:
        seq = result.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq in used:
            continue
        decision = decisions.get(seq)
        if decision is None or result.get("status") != 429 or result.get("error") is not None:
            continue
        if _same_audit_request(row, decision, result) and _inside_audit_interval(
            row, decision, result
        ):
            return seq
    return None


def unexpected_proxy_denials(item: Round) -> list[dict[str, Any]]:
    """Não confunde um 429 operacional correlacionado com recusa de escopo."""
    decisions = {
        r["seq"]: r
        for r in item.cli_rows
        if r.get("phase") == "decision"
        and r.get("decision") == "allowed"
        and isinstance(r.get("seq"), int)
        and not isinstance(r.get("seq"), bool)
    }
    results = [r for r in item.cli_rows if r.get("phase") == "result"]
    used: set[int] = set()
    unexpected = []
    for row in item.proxy_rows:
        if row.get("decision") == "allow":
            continue
        seq = _correlated_backoff(row, decisions, results, used)
        if seq is None:
            unexpected.append(row)
        else:
            used.add(seq)
    return unexpected


def _enable_writes(profile_file: Path) -> None:
    """Liga `negative.allow_writes` só na CÓPIA descartável (faz o papel da carta)."""
    text = profile_file.read_text(encoding="utf-8")
    assert "\nnegative:" not in text
    profile_file.write_text(text.rstrip("\n") + "\n" + WRITES_FLAG, encoding="utf-8", newline="\n")


def _negative_round(cli: LabCli, name: str, run_id: str) -> Round:
    """Roda `hdast negative --run` e separa só o que ESTA rodada acrescentou às trilhas."""
    cli_before = len(run_audit(cli, run_id))
    proxy_before = len(proxy_audit(cli))
    started = time.monotonic()
    done = cli.run("negative", "clinica-piloto", "--run", run_id, timeout=1500)
    seconds = round(time.monotonic() - started, 1)
    assert done.code in {0, 1, 3}, done.stdout[-800:]
    stored = json.loads((cli.runs / run_id / "negative.json").read_text(encoding="utf-8"))
    return Round(
        name=name,
        exit_code=done.code,
        seconds=seconds,
        result=stored,
        cli_rows=run_audit(cli, run_id)[cli_before:],
        proxy_rows=proxy_audit(cli)[proxy_before:],
    )


def _run_summary(cli: LabCli, *flags: str) -> dict[str, Any]:
    """Roda `hdast run` e devolve o código de saída e os estágios do `run.json`."""
    started = time.monotonic()
    done = cli.run("run", "clinica-piloto", *flags, timeout=3000)
    run_id = str(done.data.get("run_id") or done.envelope.get("run_id") or "")
    run_json = cli.runs / run_id / "run.json"
    loaded = json.loads(run_json.read_text(encoding="utf-8")) if run_json.is_file() else {}
    return {
        "flags": list(flags),
        "exit_code": done.code,
        "seconds": round(time.monotonic() - started, 1),
        "stages": {s["name"]: s for s in loaded.get("stages", [])},
    }


def _scan_for_invalid_values(cli: LabCli) -> tuple[list[str], list[str]]:
    """Arquivos das execuções e linhas da trilha do proxy com um valor proibido enviado."""
    files: list[str] = []
    for path in sorted(p for p in cli.runs.rglob("*") if p.is_file()):
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(n in text for n in INVALID_NEEDLES) or LONG_RUN.search(text):
            files.append(str(path.relative_to(cli.root)))
    proxy: list[str] = []
    for path in (cli.state / "stacks").rglob("audit.jsonl"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(n in line for n in INVALID_NEEDLES) or LONG_RUN.search(line):
                proxy.append(f"{path.parent.name}:{number}")
    return files, proxy


def _probe_after_restack(cli: LabCli, flags: list[str], seconds: dict[str, float]) -> str:
    """Sobe a pilha de novo (o perfil mudou, ADR 0081), confere o `preflight` e refaz o `probe`."""
    started = time.monotonic()
    up = cli.restack("clinica-piloto", "--build", *flags)
    assert up.code == 0, (up.stdout + up.stderr)[-1200:]
    seconds["restack"] = round(time.monotonic() - started, 1)
    preflight = cli.run("preflight", "clinica-piloto")
    assert preflight.code == 0, (preflight.stdout + preflight.stderr)[-1200:]
    started = time.monotonic()
    probe = cli.run("probe", "clinica-piloto", timeout=900)
    seconds["probe_write"] = round(time.monotonic() - started, 1)
    assert probe.code == 0, (probe.stdout + probe.stderr)[-1200:]
    return str(probe.envelope["run_id"])


def _measure(cli: LabCli, mode: str) -> NegativeLab:
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
    assert probe.code == 0, probe.stdout[-500:]
    run_id = str(probe.envelope["run_id"])
    lab = NegativeLab(mode=mode, probe_run_id=run_id, seconds=seconds)
    lab.rounds["read"] = _negative_round(cli, "read", run_id)
    started = time.monotonic()
    lab.runs["skip_scan"] = _run_summary(cli, "--skip-scan", "--no-authz")
    lab.runs["skip_scan_no_negative"] = _run_summary(
        cli, "--skip-scan", "--no-authz", "--no-negative"
    )
    seconds["run_skip_scan_pair"] = round(time.monotonic() - started, 1)
    _enable_writes(cli.products / "clinica-piloto" / "target.yml")
    lab.write_probe_run_id = _probe_after_restack(cli, flags, seconds)
    lab.rounds["write"] = _negative_round(cli, "write", lab.write_probe_run_id)
    needles = secret_values(cli, ZapHistory(cli.state_file()), PILOT_BASE)
    lab.secret_hits = files_containing(cli.runs, needles, [])
    lab.leaked_files, lab.leaked_proxy = _scan_for_invalid_values(cli)
    return lab


def _round_observations(item: Round) -> dict[str, Any]:
    result = item.result
    statuses = Counter(str(r["status"]) for r in item.sent())
    classes = {
        c["case_class"]: {k: c[k] for k in ("planned", "sent", "rejected", "accepted")}
        | {"server_error": c["server_error"], "inconclusive": c["inconclusive"]}
        for c in result["by_class"]
        if c["planned"] or c["sent"]
    }
    return {
        "exit_code": item.exit_code,
        "seconds": item.seconds,
        "status": result["status"],
        "stop_message": result["stop_message"],
        "requests_sent": result["requests_sent"],
        "operations_tested": result["operations_tested"],
        "accounts": result["accounts"],
        "created_resources": result["created_resources"],
        "restored_resources": result["restored_resources"],
        "by_class": classes,
        "response_status_counts": dict(statuses),
        "status_families": dict(
            Counter(
                f"{str(r['status'])[0]}xx" if r["status"] is not None else "sem resposta"
                for r in item.sent()
                if not str(r["operation_id"]).startswith("negative:restore:")
            )
        ),
        "requests_by_method": dict(Counter(r["method"] for r in item.decisions())),
        "proxy_denials_by_reason": dict(
            Counter(str(r.get("reason")) for r in item.proxy_rows if r.get("decision") != "allow")
        ),
        "unexpected_proxy_denials": len(unexpected_proxy_denials(item)),
        "cli_429_results": sum(
            r.get("phase") == "result" and r.get("status") == 429 for r in item.cli_rows
        ),
        "restore_requests": len(item.restores()),
        "findings": [
            {
                k: f[k]
                for k in (
                    "technique",
                    "proposed_severity",
                    "operation_id",
                    "method",
                    "path_template",
                    "location",
                    "field",
                    "case_class",
                    "declared",
                    "observed_status",
                    "baseline_status",
                    "restored",
                    "created",
                )
            }
            for f in result["findings"]
        ],
        "operations": [
            {
                k: o[k]
                for k in ("operation_id", "method", "sent", "rejected", "accepted", "server_error")
            }
            for o in result["operations"]
        ],
        "not_tested_by_reason": dict(Counter(n["reason"] for n in result["not_tested"])),
    }


def _observations(lab: NegativeLab) -> dict[str, Any]:
    return {
        "mode": lab.mode,
        "seconds": lab.seconds,
        "rounds": {name: _round_observations(item) for name, item in lab.rounds.items()},
        "runs": {
            name: {
                "exit_code": r["exit_code"],
                "seconds": r["seconds"],
                "negative_stage": r["stages"].get("negative"),
            }
            for name, r in lab.runs.items()
        },
        "files_with_an_invalid_value": lab.leaked_files,
        "proxy_audit_lines_with_an_invalid_value": lab.leaked_proxy,
    }


@pytest.fixture(scope="module", params=MODES)
def lab(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[NegativeLab]:
    require_docker()
    mode = str(request.param)
    cli = LabCli(tmp_path_factory.mktemp(f"negative-{mode}"), throwaway_pilot_env())
    cli.install_product("clinica-piloto", PILOT_PROFILE)
    try:
        measured = _measure(cli, mode)
        record_metrics(f"lab-negative-{mode}", _observations(measured))
        yield measured
    finally:
        cli.stack_down()


def test_the_read_round_sends_only_get_requests_and_leaves_the_writes_as_not_tested(
    lab: NegativeLab,
) -> None:
    item = lab.rounds["read"]
    assert item.result["status"] == "completed"
    assert item.result["requests_sent"] > 0
    assert {r["method"] for r in item.decisions()} == {"GET"}
    assert item.result["created_resources"] == 0
    reasons = {n["reason"] for n in item.result["not_tested"]}
    assert "writes_not_authorized" in reasons


def test_the_write_round_sends_writes_only_because_the_copy_of_the_profile_allows_them(
    lab: NegativeLab,
) -> None:
    item = lab.rounds["write"]
    assert item.result["status"] == "completed"
    assert {r["method"] for r in item.decisions()} & WRITE_METHODS
    assert "writes_not_authorized" not in {n["reason"] for n in item.result["not_tested"]}


def test_no_delete_request_left_the_harness(lab: NegativeLab) -> None:
    for item in lab.rounds.values():
        sent = {r["method"] for r in item.cli_rows} | {r["method"] for r in item.proxy_rows}
        assert "DELETE" not in sent


def test_every_request_of_the_stage_went_through_the_fence_and_none_was_out_of_scope(
    lab: NegativeLab,
) -> None:
    for item in lab.rounds.values():
        allowed = [r for r in item.decisions() if r["decision"] == "allowed"]
        assert [r for r in item.decisions() if r["decision"] != "allowed"] == []
        assert len(allowed) == item.result["requests_sent"] > 0
        assert unexpected_proxy_denials(item) == []
        answered = [r for r in item.sent() if r["status"] is not None]
        assert len(item.proxy_rows) >= len(answered)


def test_the_invalid_value_never_appears_in_an_artifact_nor_in_the_proxy_audit(
    lab: NegativeLab,
) -> None:
    assert lab.leaked_files == []
    assert lab.leaked_proxy == []
    for item in lab.rounds.values():
        for row in item.proxy_rows:
            assert all(
                "=" not in name and "%" not in name and len(name) <= 60
                for name in row.get("query_params", [])
            )


def test_every_accepted_or_5xx_put_or_patch_has_its_restore_recorded(lab: NegativeLab) -> None:
    item = lab.rounds["write"]
    risky = [
        r
        for r in item.sent()
        if r["method"] in {"PUT", "PATCH"}
        and not str(r["operation_id"]).startswith("negative:restore:")
        and r["status"] is not None
        and (200 <= r["status"] < 300 or r["status"] >= 500)
    ]
    assert len(item.restores()) == len(risky)
    confirmed = [r for r in item.restores() if r["status"] is not None and 200 <= r["status"] < 300]
    assert item.result["restored_resources"] == len(confirmed)
    unrestored = [
        n for n in item.result["not_tested"] if n["reason"] == "possible_unrestored_change"
    ]
    assert len(unrestored) == len(item.restores()) - len(confirmed)
    created = [
        r
        for r in item.sent()
        if r["method"] == "POST" and r["status"] is not None and 200 <= r["status"] < 300
    ]
    assert item.result["created_resources"] == len(created)


def test_negative_json_is_coherent_with_the_trail_and_with_itself(lab: NegativeLab) -> None:
    for item in lab.rounds.values():
        result = item.result
        assert result["requests_sent"] == len(item.sent())
        by_class = result["by_class"]
        for entry in by_class:
            assert entry["sent"] >= entry["rejected"] + entry["accepted"] + entry["server_error"]
        by_operation = result["operations"]
        assert sum(o["sent"] for o in by_operation) == sum(c["sent"] for c in by_class)
        assert result["operations_tested"] == len(by_operation)
        assert len(result["findings"]) == len({f["fingerprint"] for f in result["findings"]})
        assert all(f["status"] == "needs_triage" for f in result["findings"])
        assert all(f["origin"] == "negative" for f in result["findings"])


def test_run_skip_scan_records_the_negative_stage_as_skipped_with_the_right_reason(
    lab: NegativeLab,
) -> None:
    asked = lab.runs["skip_scan"]["stages"]["negative"]
    switched_off = lab.runs["skip_scan_no_negative"]["stages"]["negative"]
    assert asked["status"] == "skipped"
    assert "--skip-scan" in asked["message"]
    assert "--no-negative" not in asked["message"]
    assert switched_off["status"] == "skipped"
    assert "--no-negative" in switched_off["message"]
    assert asked["message"] != switched_off["message"]


def test_no_token_or_secret_appears_in_the_artifacts(lab: NegativeLab) -> None:
    assert lab.secret_hits == []
