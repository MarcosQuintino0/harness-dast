"""Alcance do `multipart` no `probe` (ADR 0052, T52c) contra a Clínica Piloto, nos dois modos.

Nível RÁPIDO: uma pilha por modo com a cerca deste checkout, `preflight`
e `probe --only enviarDocumento`. A operação de envio do laboratório é igual nos dois modos e não
tem falha plantada: serve só para provar que o corpo chegou ao alvo como `multipart/form-data` de
verdade (o parser do alvo leu o campo `arquivo` e devolveu 201).

Confere: o resultado `success`; o `exchanges.json` com o resumo `multipart` (partes, tamanhos),
sem corpo, sem fronteira e sem os bytes do arquivo; o pedido liberado pelo proxy, dentro da cerca,
uma vez por envio; nenhum segredo nos artefatos. O tempo de cada etapa vai para
`HDAST_IT_METRICS_DIR/lab-multipart-<modo>.json` e não vira asserção.

O que a prova não cobre: o `scan` de multipart (T52b), o `authz`, arquivos de outros tipos nem
produto real.
"""

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
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
LOGIN_PATH = "/api/auth/login"
MODES = ("vulnerable", "secure")
# Conteúdo constante do arquivo sintético de texto e assinatura do PNG sintético: nada disso pode
# ir para os artefatos.
SYNTHETIC_TEXT = "synthetic file"
PNG_SIGNATURE = "\x89PNG"


@dataclass
class MultipartLab:
    """O que foi medido em um modo, coletado enquanto a pilha dele estava no ar."""

    mode: str
    run_id: str
    probe: dict[str, Any]
    exchanges: dict[str, Any]
    proxy_rows: list[dict[str, Any]]
    cli_audit: list[dict[str, Any]]
    secret_hits: list[str]
    leaked_files: list[str]
    seconds: dict[str, float]

    def upload_results(self) -> list[dict[str, Any]]:
        """Resultados do `probe` para a operação de envio."""
        return [r for r in self.probe["operations"] if r["operation_id"] == OPERATION]

    def upload_exchanges(self) -> list[dict[str, Any]]:
        """Registros do `exchanges.json` da operação de envio."""
        return [e for e in self.exchanges["exchanges"] if e["operation_id"] == OPERATION]

    def upload_proxy_rows(self) -> list[dict[str, Any]]:
        """Linhas do proxy para o caminho do envio."""
        return [r for r in self.proxy_rows if r["path"] == UPLOAD_PATH]


def _artifact_leaks(cli: LabCli) -> list[str]:
    """Arquivos de execuções e do proxy com o conteúdo ou a assinatura do arquivo sintético."""
    found: list[str] = []
    for root in (cli.runs, cli.state / "stacks"):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if SYNTHETIC_TEXT in text or PNG_SIGNATURE in text or "�PNG" in text:
                found.append(str(path.relative_to(cli.root)))
    return found


def _measure(cli: LabCli, mode: str) -> MultipartLab:
    seconds: dict[str, float] = {}
    flags = ["--secure"] if mode == "secure" else []
    started = time.monotonic()
    up = cli.stack_up("clinica-piloto", *flags, timeout=900)
    assert up.code == 0, up.stdout[-500:]
    seconds["stack_up_build"] = round(time.monotonic() - started, 1)
    assert cli.run("preflight", "clinica-piloto").code == 0
    started = time.monotonic()
    probe = cli.run("probe", "clinica-piloto", "--only", OPERATION, timeout=900)
    seconds["probe"] = round(time.monotonic() - started, 1)
    assert probe.code == 0, probe.stdout[-800:]
    run_id = str(probe.envelope["run_id"])
    directory = cli.runs / run_id
    needles = secret_values(cli, ZapHistory(cli.state_file()), PILOT_BASE)
    hits = files_containing(cli.runs, needles, [probe.stdout, probe.stderr])
    proxy_rows = proxy_audit(cli)
    hits += [
        f"proxy:{p.name}"
        for p in (cli.state / "stacks").rglob("audit.jsonl")
        if any(n in p.read_text(encoding="utf-8", errors="replace") for n in needles)
    ]
    audit_file = directory / "audit.jsonl"
    cli_audit = [
        json.loads(line)
        for line in audit_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return MultipartLab(
        mode=mode,
        run_id=run_id,
        probe=json.loads((directory / "probe.json").read_text(encoding="utf-8")),
        exchanges=json.loads((directory / "exchanges.json").read_text(encoding="utf-8")),
        proxy_rows=proxy_rows,
        cli_audit=cli_audit,
        secret_hits=hits,
        leaked_files=_artifact_leaks(cli),
        seconds=seconds,
    )


def _observations(lab: MultipartLab) -> dict[str, Any]:
    return {
        "mode": lab.mode,
        "seconds": lab.seconds,
        "upload_results": lab.upload_results(),
        "upload_exchanges": lab.upload_exchanges(),
        "upload_proxy_rows": lab.upload_proxy_rows(),
        "probe_by_outcome": lab.probe["summary"]["by_outcome"],
    }


@pytest.fixture(scope="module", params=MODES)
def lab(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[MultipartLab]:
    require_docker()
    mode = str(request.param)
    cli = LabCli(tmp_path_factory.mktemp(f"multipart-{mode}"), throwaway_pilot_env())
    cli.install_product("clinica-piloto", PILOT_PROFILE)
    try:
        measured = _measure(cli, mode)
        record_metrics(f"lab-multipart-{mode}", _observations(measured))
        yield measured
    finally:
        cli.stack_down()


def test_the_upload_operation_succeeded_and_was_not_a_build_error(lab: MultipartLab) -> None:
    results = lab.upload_results()
    assert len(results) == 1
    assert results[0]["outcome"] == "success"
    assert lab.probe["summary"]["by_outcome"].get("build_error", 0) == 0


def test_exchanges_json_has_the_multipart_summary_without_body_or_boundary(
    lab: MultipartLab,
) -> None:
    records = lab.upload_exchanges()
    assert len(records) == 1
    record = records[0]
    assert record["method"] == "POST"
    assert record["status"] == 201
    assert record["body"] is None
    assert record["content_type"] == "multipart/form-data"
    assert "boundary" not in json.dumps(record).lower()
    parts = record["multipart"]["parts"]
    files = [p for p in parts if p["kind"] == "file"]
    assert [p["name"] for p in files] == ["arquivo"]
    assert files[0]["size"] > 0
    assert files[0]["content_type"] == "text/plain"
    assert record["multipart"]["total_bytes"] == sum(p["size"] for p in parts)


def test_no_artifact_contains_the_synthetic_file_bytes(lab: MultipartLab) -> None:
    assert lab.leaked_files == []


def test_the_proxy_released_the_upload_inside_the_fence_once_per_send(lab: MultipartLab) -> None:
    rows = lab.upload_proxy_rows()
    assert rows
    assert {r["method"] for r in rows} == {"POST"}
    assert {r["decision"] for r in rows} == {"allow"}
    sent = [
        r
        for r in lab.cli_audit
        if r["phase"] == "result" and r["method"] == "POST" and r["path"] == UPLOAD_PATH
    ]
    assert len(rows) == len(sent) == 1
    # O limite de logins do perfil faz a cerca recusar logins com `rate_backoff` (429); isso é
    # carga, não escopo. Qualquer outra recusa continua proibida.
    throttled = [r for r in lab.proxy_rows if r["reason"] == "rate_backoff"]
    assert all(r["path"] == LOGIN_PATH and r["status"] == 429 for r in throttled), throttled
    denied = [
        r for r in lab.proxy_rows if r["decision"] != "allow" and r["reason"] != "rate_backoff"
    ]
    assert denied == []


def test_no_token_or_secret_appears_in_the_artifacts_audits_or_cli_output(
    lab: MultipartLab,
) -> None:
    assert lab.secret_hits == []
