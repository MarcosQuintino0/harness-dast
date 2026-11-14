"""Apoio dos testes de integração do laboratório: CLI como processo, pilha e leitura do ZAP.

Tudo roda contra o Docker local e os alvos do próprio projeto (`vampi` e `clinica-piloto`),
com a CLI real (`python -m harness_dast`) e o ZAP e o proxy de escopo reais. Cada chamada à
CLI e ao Docker tem tempo limite; sem Docker o teste é pulado, nunca falha.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from harness_dast.adapters.storage.approval_store import FileApprovalStore
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.application.cleanup import CleanupReport, CleanupRequest
from harness_dast.cli.composition import build_cleanup
from harness_dast.domain.cleanup_plan import CleanupPlan
from harness_dast.domain.errors import ConfigError
from harness_dast.observability.logging import SecretRegistry
from tests.fakes.approvals import approval_for

REPO = Path(__file__).resolve().parents[2]
PILOT_PROFILE = REPO / "lab" / "pilot" / "product-profile"
VAMPI_PROFILE = REPO / "lab" / "vampi" / "product-profile"
VAMPI_OPENAPI = REPO / "lab" / "vampi" / "openapi3.yml"
PILOT_MANAGEMENT = "http://127.0.0.1:29091"
STACK_UP_TIMEOUT = 420
CLI_TIMEOUT = 420
DOCKER_PROBE_TIMEOUT = 25


def docker_ready() -> bool:
    """Diz se o motor do Docker responde (com tempo limite)."""
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        done = subprocess.run(  # noqa: S603 - comando fixo, sem entrada externa
            [docker, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            timeout=DOCKER_PROBE_TIMEOUT,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return done.returncode == 0


def require_docker() -> None:
    """Pula o teste quando o Docker não está disponível."""
    if not docker_ready():
        pytest.skip("Docker indisponível: o teste de integração precisa do motor do Docker.")


@dataclass(frozen=True)
class CliResult:
    """Resultado de uma chamada à CLI.

    Attributes:
        code: Código de saída.
        envelope: Envelope JSON de `stdout`, ou `{}` se não era JSON.
        stdout: Saída padrão.
        stderr: Saída de erro.
    """

    code: int
    envelope: dict[str, Any]
    stdout: str
    stderr: str

    @property
    def data(self) -> dict[str, Any]:
        """Campo `data` do envelope (vazio se ausente)."""
        found = self.envelope.get("data")
        return found if isinstance(found, dict) else {}


class TypedName:
    """Dublê do terminal: a pessoa digita `typed` no prompt (só o nome do produto confirma)."""

    def __init__(self, typed: str) -> None:
        """Guarda o que a pessoa digitou."""
        self.typed = typed

    def confirm(self, plan: CleanupPlan) -> bool:
        """Devolve `True` só se o digitado for exatamente o nome do produto."""
        return self.typed.strip() == plan.product


class LabCli:
    """Chama `python -m harness_dast --json ...` num ambiente isolado em pastas temporárias."""

    def __init__(self, root: Path, extra_env: Mapping[str, str]) -> None:
        """Cria o ambiente.

        Args:
            root: Pasta temporária da sessão (estado, execuções e produtos ficam dentro).
            extra_env: Variáveis adicionais (credenciais descartáveis dos alvos).
        """
        self.root = root
        self.products = root / "products"
        self.runs = root / "runs"
        self.state = root / "state"
        for folder in (self.products, self.runs, self.state):
            folder.mkdir(parents=True, exist_ok=True)
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("HDAST_", "PILOT_", "VAMPI_"))
        }
        env.update(
            {
                "HDAST_STATE_DIR": str(self.state),
                "HDAST_RUNS_DIR": str(self.runs),
                "HDAST_PRODUCTS_DIR": str(self.products),
                "PYTHONIOENCODING": "utf-8",
            }
        )
        env.update(extra_env)
        self.env = env

    def approve_installed_products(self) -> None:
        """Faz o que a PESSOA faria no terminal: aprova o escopo de cada produto instalado.

        O laboratório de integração prova o ZAP, o proxy e o alvo, não a aprovação (ela tem os
        próprios testes de contrato). É chamado antes de cada comando; gravar de novo a
        mesma aprovação é inofensivo, e o teste que edita o perfil depois de instalar não
        precisa lembrar de aprovar de novo.
        """
        store = FileApprovalStore(default_state_dir(self.env))
        repository = FileProfileRepository(self.products)
        for folder in sorted(self.products.iterdir()):
            if not (folder / "target.yml").is_file():
                continue
            try:
                profile = repository.load(folder.name)
            except ConfigError:
                continue  # perfil inválido de propósito: a CLI o recusa pelo próprio erro
            store.write(approval_for(profile))

    def confirm_cleanup_as_person(self, product: str, run_id: str, typed: str) -> CleanupReport:
        """Roda o caso de uso `cleanup` EM PROCESSO com a pessoa (dublê) num terminal interativo.

        A confirmação real exige terminal, que o subprocesso do teste não tem; por isso este
        caminho usa o mesmo caso de uso e o mesmo executor da CLI, com o ambiente do laboratório.
        """
        self.approve_installed_products()
        with patch.dict(os.environ, self.env):
            use_case = build_cleanup(self.products, SecretRegistry(), TypedName(typed))
            return use_case.execute(
                CleanupRequest(
                    product=product,
                    run_id=run_id,
                    dry_run=False,
                    confirm_token=None,
                    interactive=True,
                )
            )

    def run(self, *args: str, timeout: int = CLI_TIMEOUT) -> CliResult:
        """Executa a CLI e devolve código, envelope e saídas (antes, aprova os produtos)."""
        self.approve_installed_products()
        done = subprocess.run(  # noqa: S603 - interpretador atual e módulo do próprio projeto
            [sys.executable, "-m", "harness_dast", "--json", *args],
            env=self.env,
            stdin=subprocess.DEVNULL,  # nunca um terminal: o `cleanup` de verdade tem de recusar
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
            cwd=REPO,
        )
        try:
            parsed = json.loads(done.stdout)
        except ValueError:
            parsed = {}
        return CliResult(
            done.returncode, parsed if isinstance(parsed, dict) else {}, done.stdout, done.stderr
        )

    def install_product(self, name: str, source: Path, extra_files: tuple[Path, ...] = ()) -> Path:
        """Copia um perfil para `products/<name>/` (a pasta leva o nome do produto)."""
        target = self.products / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        for extra in extra_files:
            shutil.copy2(extra, target / extra.name)
        return target

    def state_file(self) -> dict[str, Any]:
        """Conteúdo do arquivo de estado da pilha (chave do ZAP, URLs); só para testes."""
        loaded = json.loads((self.state / "stack.json").read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        return loaded

    def stack_down(self) -> None:
        """Derruba a pilha, sem falhar se ela já não existe."""
        self.run("stack", "down", timeout=240)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Lê um arquivo JSON Lines (vazio se o arquivo não existe)."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def proxy_audit(cli: LabCli) -> list[dict[str, Any]]:
    """Trilha de auditoria do proxy de escopo da pilha atual."""
    status = cli.run("stack", "status")
    audit_file = status.data.get("audit_file")
    assert isinstance(audit_file, str), status.stdout
    return read_jsonl(Path(audit_file))


def run_audit(cli: LabCli, run_id: str) -> list[dict[str, Any]]:
    """Trilha de auditoria da CLI (`runs/<run_id>/audit.jsonl`)."""
    return read_jsonl(cli.runs / run_id / "audit.jsonl")


def manifest(cli: LabCli, run_id: str) -> dict[str, Any]:
    """`manifest.json` de uma execução."""
    loaded = json.loads((cli.runs / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


class ZapView:
    """Leitura do histórico e dos contextos do ZAP real (somente consulta)."""

    def __init__(self, state: Mapping[str, Any]) -> None:
        """Cria o leitor com a URL e a chave que a pilha guardou."""
        self._base = str(state["zap_url"])
        self._headers = {"X-ZAP-API-KEY": str(state["zap_api_key"])}

    def _get(self, path: str, **params: str) -> dict[str, Any]:
        response = httpx.get(
            self._base + path, params=params, headers=self._headers, timeout=30, trust_env=False
        )
        loaded = response.json()
        assert isinstance(loaded, dict), loaded
        return loaded

    def proxied_messages(self, baseurl: str) -> list[dict[str, Any]]:
        """Mensagens realmente enviadas pelo proxy do ZAP (tipo 1) para `baseurl`."""
        found = self._get("/JSON/core/view/messages/", baseurl=baseurl, start="0", count="1000")
        messages = found["messages"]
        assert isinstance(messages, list)
        return [m for m in messages if str(m["type"]) == "1"]

    def context_regexes(self, name: str) -> tuple[list[str], list[str]]:
        """Expressões de inclusão e exclusão do contexto `name`."""
        inc = self._get("/JSON/context/view/includeRegexs/", contextName=name)["includeRegexs"]
        exc = self._get("/JSON/context/view/excludeRegexs/", contextName=name)["excludeRegexs"]
        return list(inc), list(exc)

    def contexts(self) -> list[str]:
        """Nomes dos contextos existentes."""
        names = self._get("/JSON/context/view/contextList/")["contextList"]
        return [str(n) for n in names]


def request_line(message: Mapping[str, Any]) -> tuple[str, str]:
    """Método e URL da primeira linha do cabeçalho de requisição de uma mensagem do ZAP."""
    method, url, *_ = str(message["requestHeader"]).split("\r\n", 1)[0].split(" ")
    return method, url


def in_context(url: str, includes: list[str], excludes: list[str]) -> bool:
    """Diz se a URL casa com alguma inclusão e nenhuma exclusão do contexto."""
    return any(re.fullmatch(r, url) for r in includes) and not any(
        re.fullmatch(r, url) for r in excludes
    )


def target_zap_requests(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(método, caminho) das requisições da trilha da CLI enviadas pelo ZAP (rota `zap`)."""
    return [
        (row["method"], row["path"])
        for row in rows
        if row["phase"] == "decision" and row["route"] == "zap" and row["decision"] == "allowed"
    ]


def pilot_state() -> dict[str, Any]:
    """Estado de avaliação do alvo piloto (`/internal/eval/state`, porta de gestão)."""
    response = httpx.get(PILOT_MANAGEMENT + "/internal/eval/state", timeout=15, trust_env=False)
    loaded = response.json()
    assert isinstance(loaded, dict)
    return loaded
