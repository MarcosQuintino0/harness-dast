"""Apoio dos testes de ponta a ponta do `hdast run`: cenário, métricas, segredos e memória.

Cada cenário sobe a pilha real, roda `hdast run` num processo e junta tudo o que os testes
conferem: artefatos, trilha do proxy, histórico do ZAP e estado do alvo. As medidas vão para
`HDAST_IT_METRICS_DIR/<nome>.json` quando a variável existe (usado para o relatório do lab).
"""

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from tests.integration.lab_support import (
    PILOT_MANAGEMENT,
    REPO,
    CliResult,
    LabCli,
    ZapView,
    proxy_audit,
)

MiB = 1.0
_UNITS = {"KiB": 1 / 1024, "MiB": 1.0, "GiB": 1024.0}


class MemorySampler:
    """Amostra a memória dos contêineres a cada `interval` segundos e guarda o pico por nome."""

    def __init__(self, interval: float = 15.0) -> None:
        self.peaks: dict[str, float] = {}
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def __enter__(self) -> "MemorySampler":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=30)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(self._interval)

    def _sample(self) -> None:
        try:
            done = subprocess.run(  # noqa: S603 - comando fixo do teste
                [
                    shutil.which("docker") or "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.Name}} {{.MemUsage}}",
                ],
                capture_output=True,
                text=True,
                timeout=40,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return
        for line in done.stdout.splitlines():
            match = re.match(r"(\S+) ([\d.]+)(KiB|MiB|GiB) /", line)
            if match and match.group(1).startswith("hdast"):
                value = float(match.group(2)) * _UNITS[match.group(3)]
                self.peaks[match.group(1)] = max(self.peaks.get(match.group(1), 0.0), value)


@dataclass
class Scenario:
    """Resultado de um `hdast run` completo e do que ficou para trás.

    Attributes:
        name: Nome do cenário (arquivo de métricas).
        cli: Ambiente da CLI.
        result: Resultado do `run`.
        run_dir: Pasta da execução.
        audit: Trilha do proxy (toda a pilha, inclusive o login).
        peaks: Pico de memória por contêiner, em MiB.
        seconds: Duração do `run` (relógio de parede).
    """

    name: str
    cli: LabCli
    result: CliResult
    run_dir: Path
    audit: list[dict[str, Any]]
    peaks: dict[str, float]
    seconds: float
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def run_id(self) -> str:
        return str(self.result.data["run_id"])

    def load(self, name: str) -> dict[str, Any]:
        loaded = json.loads((self.run_dir / name).read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        return loaded

    @property
    def findings(self) -> list[dict[str, Any]]:
        return list(self.load("findings.json")["findings"])

    def finding_titles(self) -> Counter[str]:
        return Counter(f["title"] for f in self.findings)

    def by_severity(self) -> Counter[str]:
        return Counter(f["proposed_severity"] for f in self.findings)


def run_scenario(
    name: str, cli: LabCli, *flags: str, product: str, timeout: int = 3600
) -> Scenario:
    """Roda `hdast run <product>` medindo duração e memória, e junta os artefatos."""
    started = time.monotonic()
    with MemorySampler() as sampler:
        result = cli.run("run", product, *flags, timeout=timeout)
    seconds = time.monotonic() - started
    run_id = str(result.data.get("run_id") or result.envelope.get("run_id") or "")
    scenario = Scenario(
        name, cli, result, cli.runs / run_id, proxy_audit(cli), dict(sampler.peaks), seconds
    )
    save_metrics(scenario)
    return scenario


def save_metrics(scenario: Scenario) -> None:
    """Grava as medidas do cenário em `HDAST_IT_METRICS_DIR`, se definido."""
    target = os.environ.get("HDAST_IT_METRICS_DIR")
    if not target or not (scenario.run_dir / "scan.json").exists():
        return
    scan = scenario.load("scan.json")
    findings = (
        scenario.load("findings.json") if (scenario.run_dir / "findings.json").exists() else {}
    )
    metrics = {
        "name": scenario.name,
        "exit_code": scenario.result.code,
        "seconds": round(scenario.seconds, 1),
        "peak_memory_mib": {k: round(v) for k, v in scenario.peaks.items()},
        "run": scenario.result.data,
        "scan_status": scan["status"],
        "traffic": scan.get("traffic"),
        "entries": [
            {k: e[k] for k in ("operation_id", "outcome", "progress", "requests", "alert_count")}
            for e in scan["entries"]
        ],
        "skipped": [{"op": s["operation_id"], "reason": s["reason"]} for s in scan["skipped"]],
        "alerts_by_risk": scan["alerts_by_risk"],
        "findings": [
            {
                k: f.get(k)
                for k in ("title", "proposed_severity", "method", "path_template", "attribution")
            }
            for f in findings.get("findings", [])
        ],
    }
    folder = Path(target)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{scenario.name}.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )


class ZapHistory(ZapView):
    """`ZapView` com a leitura das mensagens do varredor e das regras do Replacer."""

    def scanner_messages(self, baseurl: str) -> list[dict[str, Any]]:
        """Mensagens enviadas pelo varredor ativo (tipo 14 no ZAP 2.17)."""
        out: list[dict[str, Any]] = []
        start = 0
        while True:
            page = self._get(
                "/JSON/core/view/messages/", baseurl=baseurl, start=str(start), count="500"
            )["messages"]
            out.extend(page)
            if len(page) < 500:
                break
            start += 500
        return [m for m in out if str(m["type"]) == "14"]

    def all_messages(self, baseurl: str) -> list[dict[str, Any]]:
        """Todas as mensagens do histórico sob `baseurl`."""
        found = self._get("/JSON/core/view/messages/", baseurl=baseurl, start="0", count="100000")
        return list(found["messages"])

    def replacer_descriptions(self) -> list[str]:
        """Descrições de todas as regras do Replacer."""
        return [str(r["description"]) for r in self._get("/JSON/replacer/view/rules/")["rules"]]


def writes(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mensagens de `POST`, `PUT` e `PATCH`."""
    return [
        m for m in messages if str(m["requestHeader"]).split(" ", 1)[0] in {"POST", "PUT", "PATCH"}
    ]


def denied_by_proxy(message: dict[str, Any]) -> bool:
    """Se o proxy de escopo negou a requisição (a resposta carrega `X-Hdast-Reason`)."""
    return "x-hdast-reason" in str(message["responseHeader"]).lower()


def csrf_rejected(message: dict[str, Any]) -> bool:
    """Se o alvo respondeu com o erro de CSRF do piloto."""
    return "XSRF_INVALIDO" in str(message["responseBody"])


def secret_values(cli: LabCli, history: ZapHistory, baseurl: str) -> list[str]:
    """Valores sensíveis reais da pilha: senhas do ambiente, bearer, XSRF e a chave do ZAP."""
    values = [
        v
        for k, v in cli.env.items()
        if k.endswith("PASSWORD") and v and k.startswith(("PILOT_", "VAMPI_"))
    ]
    values.append(str(cli.state_file()["zap_api_key"]))
    for message in history.all_messages(baseurl):
        header = str(message["requestHeader"])
        values += re.findall(r"Bearer ([\w.\-]{20,})", header)
        values += re.findall(r"(?i)x-xsrf-token: ([\w\-]{8,})", header)
    return sorted({v for v in values if len(v) >= 6})


def files_containing(root: Path, needles: list[str], extra_text: list[str]) -> list[str]:
    """Arquivos de `root` (e textos extras) que contêm algum dos valores (sem imprimi-los)."""
    hits: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(n in text for n in needles):
            hits.append(str(path.relative_to(root)))
    for index, text in enumerate(extra_text):
        if any(n in text for n in needles):
            hits.append(f"texto-extra-{index}")
    return hits


def popen_run(cli: LabCli, *args: str) -> subprocess.Popen[str]:
    """Inicia `hdast run` em segundo plano (para o teste da trava de emergência)."""
    return subprocess.Popen(  # noqa: S603 - interpretador atual e módulo do próprio projeto
        [sys.executable, "-m", "harness_dast", "--json", "run", *args],
        env=cli.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=REPO,
    )


def parse_ts(value: str) -> float:
    """Epoch de um carimbo ISO 8601."""
    return datetime.fromisoformat(value).timestamp()


def pilot_requests_by_endpoint(management: str) -> dict[str, int]:
    """Contadores por endpoint do estado de avaliação do piloto."""
    loaded = httpx.get(management + "/internal/eval/state", timeout=15, trust_env=False).json()
    return dict(loaded["requests_by_endpoint"])


def record_kill_metrics(outcome: dict[str, Any]) -> None:
    """Grava a medição da trava de emergência (sem stdout e stderr) em `HDAST_IT_METRICS_DIR`."""
    target = os.environ.get("HDAST_IT_METRICS_DIR")
    if not target:
        return
    keep = {k: v for k, v in outcome.items() if k not in {"stdout", "stderr"}}
    folder = Path(target)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "kill-switch.json").write_text(
        json.dumps(keep, indent=2, default=str), encoding="utf-8"
    )


def record_metrics(name: str, payload: dict[str, Any]) -> None:
    """Grava medidas avulsas de um teste em `HDAST_IT_METRICS_DIR/<name>.json`, se definido."""
    target = os.environ.get("HDAST_IT_METRICS_DIR")
    if not target:
        return
    folder = Path(target)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


@dataclass
class Facts:
    """O que foi medido em um cenário, coletado enquanto a pilha dele estava no ar."""

    scenario: Scenario
    rules_left: list[str] = field(default_factory=list)
    secret_hits: list[str] = field(default_factory=list)
    csrf: dict[str, int] = field(default_factory=dict)
    target_endpoints: dict[str, int] = field(default_factory=dict)
    notifications: int | None = None
    auth_on_scanner: tuple[int, int] = (0, 0)


def throwaway_pilot_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for name in ("ADMIN", "MEDICO", "PACIENTE_A", "PACIENTE_B"):
        env[f"PILOT_{name}_USERNAME"] = f"it_{secrets.token_hex(4)}"
        env[f"PILOT_{name}_PASSWORD"] = secrets.token_urlsafe(18)
    return env


def collect_facts(scenario: Scenario, base: str, *, pilot: bool) -> Facts:
    history = ZapHistory(scenario.cli.state_file())
    facts = Facts(scenario)
    facts.rules_left = [r for r in history.replacer_descriptions() if r.startswith("hdast-")]
    needles = secret_values(scenario.cli, history, base)
    facts.secret_hits = files_containing(
        scenario.cli.runs, needles, [scenario.result.stdout, scenario.result.stderr]
    )
    state_dir = scenario.cli.state / "stacks"
    facts.secret_hits += [
        f"proxy:{p.name}"
        for p in state_dir.rglob("audit.jsonl")
        if any(n in p.read_text(encoding="utf-8", errors="replace") for n in needles)
    ]
    scanner = history.scanner_messages(base)
    sent = [m for m in writes(scanner) if not denied_by_proxy(m)]
    rejected = [m for m in sent if csrf_rejected(m)]
    facts.csrf = {
        "scanner_messages": len(scanner),
        "writes_reached_target": len(sent),
        "csrf_rejected": len(rejected),
        "writes_with_header": sum("x-xsrf-token" in str(m["requestHeader"]).lower() for m in sent),
        "writes_with_cookie": sum("xsrf-token=" in str(m["requestHeader"]).lower() for m in sent),
    }
    facts.auth_on_scanner = (
        sum("authorization:" in str(m["requestHeader"]).lower() for m in scanner),
        len(scanner),
    )
    if pilot:
        facts.target_endpoints = pilot_requests_by_endpoint(PILOT_MANAGEMENT)
    return facts
