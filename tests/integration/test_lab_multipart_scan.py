"""`scan` do envio de arquivo (ADR 0052, T52b) contra a Clínica Piloto, nos dois modos.

Nível RÁPIDO: duas subidas por modo, antes e depois da edição do perfil. Cada subida tem
`preflight` e `probe --only enviarDocumento`. A segunda inclui a prova de que o scan pula a
operação.

O perfil é uma CÓPIA descartável com `scan.allow_upload_scan: true` acrescentado só nela: ali isso
faz o papel da carta autorizando a varredura de upload (o perfil do laboratório versionado não o
tem). Antes de ligar o campo, o teste também confere o caminho sem a carta: `scan --dry-run` pula a
operação com `upload_scan_not_authorized`.

O critério do ADR 0052 (seção 4) para o ZAP varrer `multipart`: a entrada do `scan.json` da operação
tem `requests > 0` E há, na trilha do proxy e no histórico do ZAP, mensagem àquele caminho com
cabeçalho `multipart/form-data` que não é a do `probe`. MEDIDO (ZAP 2.17, nos dois modos, antes do
desvio): a API `ascan/action/scan` recusou a operação com `url_not_found`, sem requisição do
varredor; o critério não foi atendido e o desvio do ADR valeu (`MULTIPART_SCANNABLE = False` em
`domain/scan_plan.py`). Este teste afirma o desvio: a operação é alcançada, pulada com
`multipart_not_scannable` e o varredor não envia nada a ela. Se a constante voltar a `True`, ele
falha e a medição acima precisa ser refeita (`requests > 0` e mensagem `multipart` do varredor).
O resultado vai para `HDAST_IT_METRICS_DIR/lab-multipart-scan-<modo>.json`.

O que a prova não cobre: o `authz`, arquivos de outros tipos nem produto real.
"""

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tests.integration.lab_support import PILOT_PROFILE, LabCli, proxy_audit, require_docker
from tests.integration.run_support import (
    ZapHistory,
    files_containing,
    record_metrics,
    secret_values,
    throwaway_pilot_env,
)

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

PILOT_BASE = "http://clinica-piloto:8080"
OPERATION = "enviarDocumento"
UPLOAD_PATH = "/api/documentos/enviar"
MODES = ("vulnerable", "secure")
UPLOAD_FLAG = "\nscan:\n  allow_upload_scan: true\n"


@dataclass
class UploadScan:
    """O que foi medido em um modo, coletado enquanto a pilha dele estava no ar."""

    mode: str
    run_id: str
    dry_without_permission: dict[str, Any]
    dry_with_permission: dict[str, Any]
    scan_exit: int
    scan: dict[str, Any]
    proxy_rows: list[dict[str, Any]]
    zap_upload_messages: list[dict[str, Any]]
    secret_hits: list[str]
    seconds: dict[str, float] = field(default_factory=dict)

    def entry(self) -> dict[str, Any] | None:
        """Entrada do `scan.json` da operação de envio, ou `None`."""
        found = [e for e in self.scan["entries"] if e["operation_id"] == OPERATION]
        return found[0] if found else None

    def upload_proxy_rows(self) -> list[dict[str, Any]]:
        """Linhas do proxy para o caminho do envio."""
        return [r for r in self.proxy_rows if r["path"] == UPLOAD_PATH]

    def multipart_scanner_messages(self) -> list[dict[str, Any]]:
        """Mensagens do varredor (tipo 14) ao caminho do envio com cabeçalho `multipart`."""
        return [m for m in self.zap_upload_messages if str(m["type"]) == "14"]

    def probe_messages(self) -> list[dict[str, Any]]:
        """Mensagens do `probe` (tipo 1) ao caminho do envio."""
        return [m for m in self.zap_upload_messages if str(m["type"]) == "1"]


def _skipped(dry: dict[str, Any]) -> dict[str, str]:
    return {s["operation_id"]: s["reason"] for s in dry["skipped"]}


def _is_upload_multipart(message: dict[str, Any]) -> bool:
    header = str(message["requestHeader"])
    first = header.split("\r\n", 1)[0].split(" ")
    return (
        len(first) > 1
        and first[0] == "POST"
        and first[1].split("?")[0].endswith(UPLOAD_PATH)
        and "multipart/form-data" in header.lower()
    )


def _enable_upload_scan(profile_file: Path) -> None:
    """Liga o campo só na CÓPIA descartável (faz o papel da carta)."""
    text = profile_file.read_text(encoding="utf-8")
    assert "\nscan:" not in text
    profile_file.write_text(text.rstrip("\n") + "\n" + UPLOAD_FLAG, encoding="utf-8", newline="\n")


def _measure(cli: LabCli, mode: str) -> UploadScan:
    seconds: dict[str, float] = {}
    flags = ["--secure"] if mode == "secure" else []
    started = time.monotonic()
    up = cli.stack_up("clinica-piloto", *flags, timeout=900)
    assert up.code == 0, up.stdout[-500:]
    seconds["stack_up_build"] = round(time.monotonic() - started, 1)
    assert cli.run("preflight", "clinica-piloto").code == 0
    probe = cli.run("probe", "clinica-piloto", "--only", OPERATION, timeout=900)
    assert probe.code == 0, probe.stdout[-800:]
    run_id = str(probe.envelope["run_id"])
    base = ["scan", "clinica-piloto", "--run", run_id, "--only", OPERATION]
    without = cli.run(*base, "--dry-run")
    assert without.code == 0, without.stdout[-800:]
    _enable_upload_scan(cli.products / "clinica-piloto" / "target.yml")
    run_id = _probe_after_restack(cli, flags, seconds)
    return _measure_skip(cli, mode, run_id, without.data, seconds)


def _probe_after_restack(cli: LabCli, flags: list[str], seconds: dict[str, float]) -> str:
    started = time.monotonic()
    up = cli.restack("clinica-piloto", *flags)
    assert up.code == 0, (up.stdout + up.stderr)[-1200:]
    seconds["restack"] = round(time.monotonic() - started, 1)
    preflight = cli.run("preflight", "clinica-piloto")
    assert preflight.code == 0, (preflight.stdout + preflight.stderr)[-1200:]
    started = time.monotonic()
    probe = cli.run("probe", "clinica-piloto", "--only", OPERATION, timeout=900)
    assert probe.code == 0, (probe.stdout + probe.stderr)[-1200:]
    seconds["probe_with_permission"] = round(time.monotonic() - started, 1)
    return str(probe.envelope["run_id"])


def _measure_skip(
    cli: LabCli, mode: str, run_id: str, without: dict[str, Any], seconds: dict[str, float]
) -> UploadScan:
    base = ["scan", "clinica-piloto", "--run", run_id, "--only", OPERATION]
    with_permission = cli.run(*base, "--dry-run")
    assert with_permission.code == 0, with_permission.stdout[-800:]
    assert with_permission.data["planned"] == [], "O plano incluiu operações para o varredor"
    assert _skipped(with_permission.data).get(OPERATION) == "multipart_not_scannable"
    started = time.monotonic()
    live = cli.run(*base, "--max-minutes", "5", timeout=900)
    seconds["scan"] = round(time.monotonic() - started, 1)
    scan_file = cli.runs / run_id / "scan.json"
    output = (live.stdout + live.stderr)[-1200:]
    assert live.code == 0, f"O scan terminou com código {live.code}.\n{output}"
    assert scan_file.is_file(), f"O scan não gerou {scan_file}.\n{output}"
    scan = json.loads(scan_file.read_text(encoding="utf-8"))
    history = ZapHistory(cli.state_file())
    messages = [m for m in history.all_messages(PILOT_BASE) if _is_upload_multipart(m)]
    needles = secret_values(cli, history, PILOT_BASE)
    hits = files_containing(cli.runs, needles, [live.stdout, live.stderr])
    return UploadScan(
        mode=mode,
        run_id=run_id,
        dry_without_permission=without,
        dry_with_permission=with_permission.data,
        scan_exit=live.code,
        scan=scan,
        proxy_rows=proxy_audit(cli),
        zap_upload_messages=messages,
        secret_hits=hits,
        seconds=seconds,
    )


def _observations(lab: UploadScan) -> dict[str, Any]:
    entry = lab.entry()
    return {
        "mode": lab.mode,
        "seconds": lab.seconds,
        "scan_exit": lab.scan_exit,
        "scan_status": lab.scan["status"],
        "entry": entry,
        "skipped_without_permission": _skipped(lab.dry_without_permission),
        "proxy_rows_to_upload_path": len(lab.upload_proxy_rows()),
        "zap_multipart_messages_probe": len(lab.probe_messages()),
        "zap_multipart_messages_scanner": len(lab.multipart_scanner_messages()),
        "alerts_total": lab.scan.get("alerts_total"),
    }


@pytest.fixture(scope="module", params=MODES)
def lab(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[UploadScan]:
    require_docker()
    mode = str(request.param)
    cli = LabCli(tmp_path_factory.mktemp(f"multipart-scan-{mode}"), throwaway_pilot_env())
    cli.install_product("clinica-piloto", PILOT_PROFILE)
    try:
        measured = _measure(cli, mode)
        record_metrics(f"lab-multipart-scan-{mode}", _observations(measured))
        yield measured
    finally:
        cli.stack_down()


def test_without_the_permission_the_upload_is_reached_but_skipped_with_the_reason(
    lab: UploadScan,
) -> None:
    assert _skipped(lab.dry_without_permission)[OPERATION] == "upload_scan_not_authorized"


def test_with_the_permission_the_upload_is_still_skipped_because_the_zap_cannot_scan_multipart(
    lab: UploadScan,
) -> None:
    assert lab.dry_with_permission["planned"] == []
    assert _skipped(lab.dry_with_permission)[OPERATION] == "multipart_not_scannable"


def test_the_live_scan_skips_the_upload_without_asking_the_zap_and_finishes_clean(
    lab: UploadScan,
) -> None:
    assert lab.scan_exit == 0
    assert lab.scan["status"] == "completed"
    assert lab.entry() is None
    assert {s["operation_id"]: s["reason"] for s in lab.scan["skipped"]} == {
        OPERATION: "multipart_not_scannable"
    }


def test_the_probe_reached_the_upload_once_and_the_zap_scanner_sent_nothing_to_it(
    lab: UploadScan,
) -> None:
    assert len(lab.probe_messages()) == 1
    assert lab.multipart_scanner_messages() == []
    rows = lab.upload_proxy_rows()
    assert len(rows) == 1
    assert {r["method"] for r in rows} == {"POST"}
    assert {r["decision"] for r in rows} == {"allow"}


def test_no_token_or_secret_appears_in_the_artifacts_or_cli_output(lab: UploadScan) -> None:
    assert lab.secret_hits == []
