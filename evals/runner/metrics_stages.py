"""Etapa de cada chamada de ferramenta, por regra deterministica (sem modelo de linguagem).

Regra (a mesma esta no `evals/README.md`):

1. Cada comando `hdast` visto numa chamada de shell tem uma etapa propria (`STAGE_OF_COMMAND`):
   `doctor`, `init`, `profile *`, `spec *` -> `cadastro`; `probe` -> `alcance`; `stack up`,
   `preflight`, `run`, `scan`, `authz` -> `varredura`; `report` e `triage` -> `triagem`; o resto
   (`stack down`, `stack status`, `stop`, `cleanup`, `secret *`, `version`) -> `outro`.
2. Antes do primeiro comando `hdast`, tudo e `leitura` (README, skills, docs, carta).
3. Uma chamada com comando `hdast` tem a etapa do comando mais adiantado (cadastro < alcance <
   varredura < triagem); so `outro` fica em `outro` e nao muda a fase.
4. Uma chamada sem `hdast` herda a fase atual: a etapa do ultimo comando que nao era `outro`.
   Depois do primeiro comando e antes de qualquer outro, a fase e `cadastro`; o primeiro
   `profile validate` com sucesso encerra o cadastro e a fase passa a `alcance`.
5. Depois de um `run` ou `scan`, a chamada que cita `findings.json`, `report.md|html` ou `triage`
   (arquivo lido, comando) abre a `triagem`, que fica ate o fim.

O tempo de pensar (modelo gerando a proxima chamada) pertence a etapa dessa chamada; o tempo de
espera pertence a etapa da chamada que esta rodando.
"""

import re
import shlex
from dataclasses import dataclass

from evals.runner.checks_security import _typed
from evals.runner.transcript import SHELL_TOOLS, ToolCall

ORDER = ("cadastro", "alcance", "varredura", "triagem")
GROUPS = {
    "profile": frozenset({"validate"}),
    "spec": frozenset({"inspect"}),
    "stack": frozenset({"up", "down", "status"}),
    "secret": frozenset({"set", "list", "delete"}),
}
KNOWN = frozenset(
    {
        "version",
        "doctor",
        "init",
        "preflight",
        "probe",
        "scan",
        "authz",
        "report",
        "triage",
        "run",
        "cleanup",
        "stop",
        *GROUPS,
    }
)
STAGE_OF_COMMAND = {
    "doctor": "cadastro",
    "init": "cadastro",
    "profile": "cadastro",
    "spec": "cadastro",
    "probe": "alcance",
    "stack up": "varredura",
    "preflight": "varredura",
    "run": "varredura",
    "scan": "varredura",
    "authz": "varredura",
    "report": "triagem",
    "triage": "triagem",
}
SCAN_COMMANDS = frozenset({"run", "scan"})
HDAST = re.compile(r"(?<![\w./\\-])hdast(?![\w-])")
SEGMENT_END = re.compile(r"[;|&<>\n]")
FLAG = re.compile(r"^--([A-Za-z][\w-]*)")
TRIAGE_MARKER = re.compile(r"findings\.json|report\.(?:md|html)|triage", re.IGNORECASE)
READERS = re.compile(r"\b(?:cat|head|type|Get-Content)\b([^|;&<>\n]*)")


@dataclass(frozen=True)
class Invocation:
    """Um comando `hdast` visto. So o subcomando e as flags viram saida; `identity` nao."""

    label: str
    flags: tuple[str, ...]
    identity: str

    @property
    def signature(self) -> str:
        """Subcomando e nomes de flag, sem nenhum valor de argumento."""
        return " ".join([self.label, *self.flags])

    @property
    def stage(self) -> str:
        """Etapa propria do comando."""
        table = STAGE_OF_COMMAND
        return table.get(self.label, table.get(self.label.split()[0], "outro"))


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _label(tokens: list[str]) -> tuple[str, list[str]] | None:
    for index, token in enumerate(tokens):
        if token.startswith("-") or token not in KNOWN:
            continue
        rest = tokens[index + 1 :]
        sub = rest[0] if rest else ""
        if token in GROUPS and sub in GROUPS[token]:
            return f"{token} {sub}", rest[1:]
        return token, rest
    return None


def parse_hdast(command: str) -> list[Invocation]:
    """Comandos `hdast` de uma linha de shell, sem o texto de heredocs de `cat`/`tee`."""
    text = _typed(command)
    found: list[Invocation] = []
    for match in HDAST.finditer(text):
        tail = text[match.end() :]
        end = SEGMENT_END.search(tail)
        tokens = _tokens(tail[: end.start()] if end else tail)
        parsed = _label(tokens)
        if parsed is None:
            continue
        label, rest = parsed
        names = sorted({m.group(1) for t in rest if (m := FLAG.match(t)) and m.group(1) != "json"})
        flags = tuple(f"--{name}" for name in names)
        found.append(Invocation(label, flags, " ".join(tokens)))
    return found


def shell_read_paths(command: str) -> list[str]:
    """Arquivos lidos por `cat`, `head`, `type` ou `Get-Content` (nunca `tail`, que e de espera)."""
    paths: list[str] = []
    for match in READERS.finditer(_typed(command)):
        for token in _tokens(match.group(1)):
            if not token.startswith("-") and ("/" in token or "\\" in token or "." in token):
                paths.append(token)
    return paths


def _stage_rank(stage: str) -> int:
    return ORDER.index(stage) if stage in ORDER else -1


def _call_text(call: ToolCall) -> str:
    return _typed(call.command) if call.name in SHELL_TOOLS else call.target


class StageTracker:
    """Fase atual da rodada. Recebe as chamadas em ordem e diz a etapa de cada uma."""

    def __init__(self) -> None:
        self.phase = "leitura"
        self._scanned = False

    def classify(self, call: ToolCall, invocations: list[Invocation]) -> str:
        """Etapa da chamada. Atualiza a fase."""
        if invocations:
            self._scanned = self._scanned or any(i.label in SCAN_COMMANDS for i in invocations)
            stages = [item.stage for item in invocations if item.stage != "outro"]
            if not stages:
                if self.phase == "leitura":
                    self.phase = "cadastro"
                return "outro"
            self.phase = max(stages, key=_stage_rank)
            return self.phase
        if self._scanned and TRIAGE_MARKER.search(_call_text(call)):
            self.phase = "triagem"
        return self.phase

    def validated(self) -> None:
        """Um `profile validate` terminou com sucesso: o cadastro acabou."""
        if self.phase == "cadastro":
            self.phase = "alcance"
