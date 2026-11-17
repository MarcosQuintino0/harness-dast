"""Apoio à prova V1.11: processo CLI, trava e resumo sem saídas brutas."""

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness_dast.domain.authz.result import AuthzFinding
from harness_dast.domain.finding import Finding
from harness_dast.domain.negative_result import NegativeFinding
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.run import is_run_id
from harness_dast.domain.signal_result import SignalFinding
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
STOP_TIMEOUT = 20
STOP_GRACE = 30


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

    def _stop_timed_out(self, record: dict[str, Any]) -> None:
        """Pede parada ao harness sem usar novamente o executor recursivamente."""
        record["stop_exit"] = None
        try:
            check_ownership(self.token)
            stop = self.cli.run("stop", timeout=STOP_TIMEOUT)
            record["stop_exit"] = stop.code
        except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as error:
            record["stop_error"] = type(error).__name__
        self.save()

    def _kill_process_tree(self, process: subprocess.Popen[str], record: dict[str, Any]) -> None:
        """Encerra o processo e filhos no Windows, preservando o resultado no resumo."""
        if os.name == "nt":
            try:
                taskkill = (
                    Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/taskkill.exe"
                )
                result = subprocess.run(  # noqa: S603 - PID do próprio subprocesso
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    stdin=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
                record["tree_kill_exit"] = result.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                record["tree_kill_error"] = type(error).__name__
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)

    def _handle_timeout(
        self, process: subprocess.Popen[str], args: tuple[str, ...], record: dict[str, Any]
    ) -> None:
        """Sinaliza o prazo e só força o encerramento após tentativa de parada segura."""
        record["timeout"] = True
        self.save()
        try:
            if args[0] in {"run", "confirm"}:
                self._stop_timed_out(record)
                try:
                    process.communicate(timeout=STOP_GRACE)
                except subprocess.TimeoutExpired:
                    self._kill_process_tree(process, record)
            else:
                self._kill_process_tree(process, record)
        finally:
            record["exit_code"] = process.poll()
            self.save()
        raise TimeoutError(f"Prazo do comando {args[0]} excedido.")

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
                    self._handle_timeout(process, args, record)
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


def report_items(
    report: FindingsReport,
) -> tuple[Finding | AuthzFinding | NegativeFinding | SignalFinding, ...]:
    """Retorna as mesmas origens que a confirmação considera, na mesma ordem."""
    all_items: list[Finding | AuthzFinding | NegativeFinding | SignalFinding] = list(
        report.findings
    )
    for section in (report.authz, report.negative, report.proxy_signals):
        if section is not None:
            all_items.extend(section.findings)
    return tuple(all_items)


def findings(report: FindingsReport) -> dict[str, dict[str, Any]]:
    """Índice dos achados completos, incluindo severidade e identidade."""
    all_items = report_items(report)
    result = {item.fingerprint: item.model_dump(mode="json") for item in all_items}
    assert len(result) == len(all_items), "Fingerprint repetido no relatório."
    return result
