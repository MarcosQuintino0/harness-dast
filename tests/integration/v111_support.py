"""Apoio à prova V1.11: processo CLI, trava e resumo sem saídas brutas."""

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness_dast.domain.authz.result import AuthzFinding
from harness_dast.domain.finding import Finding
from harness_dast.domain.negative_result import NegativeFinding
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.run import is_run_id
from harness_dast.domain.signal_result import SignalFinding
from harness_dast.domain.verification import VerificationFile
from tests.integration.lab_support import (
    PILOT_PROFILE,
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    LabCli,
)
from tests.integration.run_support import throwaway_pilot_env
from tests.integration.test_lab_vampi import SEEDED

ARTIFACTS = Path("C:/harness-dast-artefatos/v1-11")
LOCK = ARTIFACTS.parent / "lab.lock"
WRAPPER = ARTIFACTS / "docker-bin"
TIMEOUT = 3600


def load_json(path: Path) -> dict[str, Any]:
    """Lê um objeto JSON de artefato já redigido pela CLI."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Artefato não é objeto JSON.")
    return value


def check_ownership(token: str) -> None:
    """Exige correspondência integral da trava com o documento do coordenador."""
    lock = load_json(LOCK)
    expected = load_json(ARTIFACTS / "lab-ownership.json")
    stored = lock.get("token")
    if lock != expected or lock.get("version") != "v1.11" or lock.get("owner") != "codex":
        raise ValueError("Trava global não pertence à V1.11 codex.")
    if not isinstance(stored, str) or not secrets.compare_digest(stored, token):
        raise ValueError("Token da trava global não confere.")
    if not (WRAPPER / "docker.cmd").is_file() or not (ARTIFACTS / "docker_namespace.py").is_file():
        raise ValueError("Wrapper Docker do laboratório indisponível.")


def prepare_root(root_text: str, case: str) -> Path:
    """Reserva uma subpasta nova de evidências, fora do repositório e do estado real."""
    base = Path(root_text)
    if not base.is_absolute():
        raise ValueError("V111_LAB_ROOT deve ser absoluto.")
    base = base.resolve()
    if base == ARTIFACTS.resolve() or not base.is_relative_to(ARTIFACTS.resolve()):
        raise ValueError("V111_LAB_ROOT deve ficar abaixo de artefatos/v1-11.")
    base.mkdir(parents=True, exist_ok=True)
    target = base / case
    target.mkdir(exist_ok=False)
    return target


def make_cli(root: Path, product: str) -> tuple[LabCli, str]:
    """Instala cópias exatas dos perfis de laboratório e isola a descoberta de Docker."""
    env = throwaway_pilot_env()
    if product == "vampi":
        env.update(SEEDED)
    cli = LabCli(root, env)
    cli.env.pop("V111_LOCK_TOKEN", None)
    cli.env.pop("V111_LAB_ROOT", None)
    cli.env["PATH"] = str(WRAPPER) + os.pathsep + cli.env["PATH"]
    resolved = shutil.which("docker", path=cli.env["PATH"])
    if resolved is None or Path(resolved).resolve() != (WRAPPER / "docker.cmd").resolve():
        raise ValueError("A resolução de docker não aponta para o wrapper autorizado.")
    source = PILOT_PROFILE if product == "clinica-piloto" else VAMPI_PROFILE
    extras = () if product == "clinica-piloto" else (VAMPI_OPENAPI,)
    installed = cli.install_product(product, source, extras)
    original = hashlib.sha256((source / "target.yml").read_bytes()).hexdigest()
    assert hashlib.sha256((installed / "target.yml").read_bytes()).hexdigest() == original
    return cli, original


@dataclass
class LabRun:
    """Coordena comandos e persiste apenas metadados sanitizados."""

    cli: LabCli
    token: str = field(repr=False)
    metrics: Path
    case: str
    summary: dict[str, Any]

    def save(self) -> None:
        self.metrics.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.summary, ensure_ascii=False, indent=2)
        (self.cli.root / "summary.json").write_text(text, encoding="utf-8")
        (self.metrics / f"{self.case}.json").write_text(text, encoding="utf-8")

    def command(self, *args: str, timeout: int = TIMEOUT) -> tuple[int, dict[str, Any]]:
        """Espera em ciclos sem expor stdout, stderr, credenciais ou progresso do scan."""
        check_ownership(self.token)
        started = time.monotonic()
        record: dict[str, Any] = {"args": list(args), "exit_code": None, "seconds": None}
        self.summary["commands"].append(record)
        self.save()
        process = self.cli.start(*args)
        try:
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    process.kill()
                    process.communicate()
                    record["timeout"] = True
                    raise TimeoutError(f"Prazo do comando {args[0]} excedido.")
                try:
                    stdout, _ = process.communicate(timeout=min(30, remaining))
                    break
                except subprocess.TimeoutExpired:
                    sys.stderr.write(f"V1.11 {self.case}: {args[0]} ainda em execução.\n")
            record["exit_code"] = process.returncode
            try:
                envelope = json.loads(stdout)
            except ValueError:
                envelope = {}
            return process.returncode, envelope if isinstance(envelope, dict) else {}
        finally:
            record["seconds"] = round(time.monotonic() - started, 3)
            self.save()


def run_id_for(cli: LabCli, envelope: dict[str, Any]) -> str:
    """Recupera a execução do envelope ou da única pasta criada pelo run."""
    data = envelope.get("data")
    run_id = envelope.get("run_id") or (data.get("run_id") if isinstance(data, dict) else None)
    if not isinstance(run_id, str) or not is_run_id(run_id):
        candidates = [path.parent.name for path in cli.runs.glob("*/run.json")]
        if len(candidates) != 1 or not is_run_id(candidates[0]):
            raise ValueError("Não foi possível identificar uma única execução.")
        run_id = candidates[0]
    return run_id


def findings(report: FindingsReport) -> dict[str, dict[str, Any]]:
    """Índice de identidade e severidade de todas as origens do relatório."""
    all_items: list[Finding | AuthzFinding | NegativeFinding | SignalFinding] = list(
        report.findings
    )
    for section in (report.authz, report.negative, report.proxy_signals):
        if section is not None:
            all_items.extend(section.findings)
    result = {item.fingerprint: item.model_dump(mode="json") for item in all_items}
    assert len(result) == len(all_items), "Fingerprint repetido no relatório."
    return result


def verification_summary(
    report: FindingsReport, verification: VerificationFile, confirm_data: dict[str, Any]
) -> dict[str, Any]:
    """Valida identidade, classificações e orçamento total observável."""
    assert verification.product == report.product
    assert verification.run_id == report.run_id
    known = findings(report)
    assert len(verification.entries) == min(len(known), 30)
    assert {entry.fingerprint for entry in verification.entries} <= set(known)
    for entry in verification.entries:
        assert entry.reason.strip()
        if entry.recipe is None:
            assert entry.level in {"not_verifiable", "inconclusive"}
        if entry.level == "reproduced":
            assert entry.recipe is not None
    recipe = confirm_data.get("recipe_requests")
    session = confirm_data.get("session_requests")
    assert type(recipe) is int
    assert recipe >= 0
    assert type(session) is int
    assert session >= 0
    assert recipe + session <= 12 * len(verification.entries)
    return {
        "count": len(verification.entries),
        "levels": dict(Counter(entry.level for entry in verification.entries)),
        "reasons": dict(Counter(entry.reason for entry in verification.entries)),
        "recipes": dict(Counter(entry.recipe or "none" for entry in verification.entries)),
        "recipe_requests": recipe,
        "session_requests": session,
        "per_finding_budget": "indisponível na auditoria: total agregado apenas",
    }
