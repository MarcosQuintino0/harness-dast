"""A trava por pilha (ADR 0035) contra a pilha real da Clínica Piloto (ZAP, proxy e alvo).

Um `scan --only` de uma operação roda em segundo plano (ataque direcionado, nunca a varredura
completa) e, enquanto ele roda, um segundo comando que toca o alvo é recusado com `STACK_BUSY`
(saída 8) dizendo quem ocupa. Quando o primeiro termina, a trava some e o segundo passa.
Exige Docker. Se a variável `IT_EVIDENCE_DIR` apontar para uma pasta, o teste grava ali
a linha do tempo e as saídas (sem segredo: só envelopes e mensagens da CLI).
"""

import json
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.integration.lab_support import PILOT_PROFILE, LabCli, require_docker
from tests.integration.run_support import throwaway_pilot_env

pytestmark = pytest.mark.integration

PRODUCT = "clinica-piloto"
# Leitura com parâmetro: o ataque direcionado demora o bastante para o segundo comando chegar.
ATTACKED_OPERATION = "buscarPacientesPorNome"
BUSY_EXIT = 8
LOCK_WAIT_SECONDS = 120
SCAN_TIMEOUT = 900


class Evidence:
    """Linha do tempo do teste, gravada em `IT_EVIDENCE_DIR` quando a pessoa pede."""

    def __init__(self) -> None:
        """Marca o instante zero."""
        self._start = time.monotonic()
        self.lines: list[str] = []

    def note(self, text: str) -> None:
        """Acrescenta uma linha com o tempo desde o início."""
        self.lines.append(f"[{time.monotonic() - self._start:7.1f}s] {text}")

    def save(self) -> None:
        """Grava a linha do tempo, se a pasta de evidência foi pedida."""
        folder = os.environ.get("IT_EVIDENCE_DIR")
        if folder:
            target = Path(folder)
            target.mkdir(parents=True, exist_ok=True)
            (target / "timeline.txt").write_text("\n".join(self.lines) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def cli(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LabCli]:
    require_docker()
    lab = LabCli(tmp_path_factory.mktemp("stack-lock"), throwaway_pilot_env())
    lab.install_product(PRODUCT, PILOT_PROFILE)
    try:
        assert lab.stack_up(PRODUCT, timeout=600).code == 0
        yield lab
    finally:
        lab.stack_down()


def _wait_for_lock(
    lab: LabCli, running: "subprocess.Popen[str]", evidence: Evidence
) -> dict[str, Any]:
    lock_file = lab.state / "stack.lock"
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while time.monotonic() < deadline:
        if lock_file.is_file():
            evidence.note("stack.lock apareceu")
            holder = json.loads(lock_file.read_text(encoding="utf-8"))
            assert isinstance(holder, dict)
            return holder
        assert running.poll() is None, "o scan terminou antes de tomar a trava"
        time.sleep(0.2)
    pytest.fail("o scan não tomou a trava a tempo")


def test_second_command_is_refused_while_the_first_runs_and_works_after_it_ends(
    cli: LabCli,
) -> None:
    evidence = Evidence()
    running: subprocess.Popen[str] | None = None
    try:
        assert cli.run("preflight", PRODUCT).code == 0
        probe = cli.run("probe", PRODUCT, "--seed", "1")
        assert probe.code == 0, probe.stdout[-500:]
        run_id = str(probe.envelope["run_id"])
        evidence.note(f"probe completo terminou (run {run_id}); a trava já foi solta")
        assert not (cli.state / "stack.lock").exists()

        running = cli.start(
            "scan", PRODUCT, "--run", run_id, "--max-minutes", "6", "--only", ATTACKED_OPERATION
        )
        evidence.note(f"scan --only {ATTACKED_OPERATION} iniciado (pid {running.pid})")
        holder = _wait_for_lock(cli, running, evidence)
        # No Windows o `python.exe` do venv é um lançador: o PID da trava é o do processo filho,
        # que não é o do `Popen`. Por isso a trava é conferida pelo comando e pelo produto, e a
        # mensagem de recusa pelo PID que a própria trava registrou.
        assert (holder["command"], holder["product"]) == ("scan", PRODUCT)

        status = cli.run("stack", "status")
        assert status.data["lock"]["state"] == "held"
        evidence.note("stack status mostra a trava como held")

        refused = cli.run("probe", PRODUCT, "--only", "criarConvenio", "--seed", "2")
        evidence.note(f"segundo comando (probe): saída {refused.code}")
        evidence.note(f"mensagem: {refused.envelope.get('error', {}).get('message')}")
        assert running.poll() is None, "o scan acabou antes do segundo comando: prova inválida"
        assert refused.code == BUSY_EXIT, refused.stdout
        error = refused.envelope["error"]
        assert error["code"] == "STACK_BUSY"
        assert "scan" in error["message"]
        assert PRODUCT in error["message"]
        assert str(holder["pid"]) in error["message"]

        stdout, stderr = running.communicate(timeout=SCAN_TIMEOUT)
        evidence.note(f"scan terminou com saída {running.returncode}")
        assert running.returncode in {0, 3}, stdout[-500:] + stderr[-500:]
        assert not (cli.state / "stack.lock").exists(), "a trava deveria ter sido solta"
        assert cli.run("stack", "status").data["lock"] is None

        after = cli.run("probe", PRODUCT, "--only", "criarConvenio", "--seed", "2")
        evidence.note(f"mesmo comando depois do fim do primeiro: saída {after.code}")
        assert after.code == 0, after.stdout[-500:]
        assert not (cli.state / "stack.lock").exists()
    finally:
        if running is not None and running.poll() is None:
            cli.run("stop")  # parada de emergência: sem isto o `stack down` seria recusado
            running.communicate(timeout=SCAN_TIMEOUT)
        evidence.save()
