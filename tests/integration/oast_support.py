"""Apoio exclusivo à prova de Callback com emissor sintético em rede interna."""

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import httpx

from tests.integration.lab_support import REPO, CliResult, LabCli
from tests.integration.oast_cleanup import CleanupResult, OastCleanup

PYTHON_IMAGE = (
    "python:3.13-slim-bookworm@sha256:"
    "a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72"
)
PROJECT = "hdast-codex"
CRAPI_PROJECT = "hdast-crapi-codex"


class OastLab:
    """Controla somente o overlay e o contêiner efêmero próprios da prova."""

    def __init__(
        self,
        cli: LabCli,
        key: str,
        nonce: str,
        runner: Callable[[tuple[str, ...]], str] | None = None,
    ) -> None:
        self.cli = cli
        self.key = key
        if not re.fullmatch(r"[0-9a-f]{12}", nonce):
            raise ValueError("identificador da prova inválido")
        self._runner = runner
        self.network = f"hdast-oast-{nonce}"
        self.client = f"hdast-oast-client-{nonce}"
        self.cli.env["HDAST_OAST_NETWORK"] = self.network
        self.cli.env["HDAST_LAB_NETWORK"] = PROJECT + "_lab_net"
        self.cli.env["HDAST_OAST_OWNER"] = nonce
        self.cleanup = OastCleanup(
            lambda args: self.docker(*args), nonce, self.network, self.client
        )
        self.stack_intended = False
        self._project_checked = False
        self._crapi_checked = False

    def docker(self, *args: str) -> str:
        """Executa comando explícito de suporte Docker, com timeout."""
        if self._runner is not None:
            return self._runner(args)
        executable = shutil.which("docker")
        if executable is None:
            raise FileNotFoundError("Docker indisponível")
        done = subprocess.run(  # noqa: S603 - argumentos restritos do próprio teste
            [executable, *args],
            cwd=REPO,
            env=self.cli.env,
            text=True,
            capture_output=True,
            timeout=90,
            check=True,
        )
        return done.stdout.strip()

    def compose(self, *args: str) -> str:
        """Seleciona o mesmo projeto e os dois arquivos da ponte."""
        return self.docker(
            "compose",
            "-p",
            PROJECT,
            "-f",
            "compose.yaml",
            "-f",
            "lab/oast/compose.yaml",
            "-f",
            "tests/integration/oast-owner.compose.yaml",
            *args,
        )

    def api(self, endpoint: str, **params: str) -> dict[str, object]:
        """Consulta a API de controle do ZAP com a chave sintética desta prova."""
        response = httpx.get(
            "http://127.0.0.1:8080/JSON/" + endpoint + "/",
            params=params,
            headers={"X-ZAP-API-KEY": self.key},
            timeout=30,
            trust_env=False,
        )
        response.raise_for_status()
        result = response.json()
        assert isinstance(result, dict), result
        assert "code" not in result, result
        return result

    def start(self, *, synthetic: bool = True) -> None:
        """Cria o gateway sem recriar nem adicionar redes ao ZAP."""
        self.cleanup.gateway_intended = True
        self.compose("up", "-d", "--no-deps", "oast-gateway")
        if synthetic:
            self.cleanup.client_intended = True
            self.docker(
                "run",
                "-d",
                "--pull=never",
                "--name",
                self.client,
                "--label",
                "io.hdast.oast.owner=" + self.cleanup.owner,
                "--network",
                self.network,
                "--entrypoint",
                "python",
                PYTHON_IMAGE,
                "-c",
                "import time; time.sleep(300)",
            )
        self.api(
            "oast/action/setCallbackOptions",
            localAddress="0.0.0.0",  # noqa: S104 - somente rede interna do ZAP
            remoteAddress="oast-gateway",
            port="8090",
        )

    def assert_project_unused(self) -> None:
        """Não reutiliza contêineres ou redes de outra sessão do projeto."""
        label = "label=com.docker.compose.project=" + PROJECT
        assert not self.docker("ps", "-aq", "--filter", label)
        assert not self.docker("network", "ls", "-q", "--filter", label)
        assert not self.docker("network", "ls", "-q", "--filter", f"name=^{self.network}$")
        assert not self.docker("ps", "-aq", "--filter", f"name=^/{self.client}$")
        for suffix in ("zap_net", "lab_net", "egress_net", "host_net"):
            assert not self.docker("network", "ls", "-q", "--filter", f"name=^{PROJECT}_{suffix}$")
        self._project_checked = True

    def assert_crapi_unused(self) -> None:
        """Não reutiliza recursos crAPI de outra sessão."""
        label = "label=com.docker.compose.project=" + CRAPI_PROJECT
        assert not self.docker("ps", "-aq", "--filter", label)
        assert not self.docker("network", "ls", "-q", "--filter", label)
        assert not self.docker("volume", "ls", "-q", "--filter", label)
        for suffix in ("crapi_net", "publish_net"):
            assert not self.docker(
                "network", "ls", "-q", "--filter", f"name=^{CRAPI_PROJECT}_{suffix}$"
            )
        self._crapi_checked = True

    def stack_up(self, product: str) -> CliResult:
        """Registra intenção antes de subir projeto comprovadamente livre."""
        if not self._project_checked or (product == "crapi" and not self._crapi_checked):
            raise ValueError("projetos não verificados")
        if product not in {"vampi", "crapi"}:
            raise ValueError("alvo de prova inválido")
        self.stack_intended = True
        result = self.cli.run("stack", "up", product, timeout=900)
        if result.code == 0:
            self.cleanup.capture_stack()
        return result

    def crapi_compose(self, *args: str) -> str:
        """Usa o overlay do workshop com ambiente sintético de teste."""
        return self.docker(
            "compose",
            "-p",
            CRAPI_PROJECT,
            "-f",
            "lab/crapi/compose.yaml",
            "-f",
            "lab/crapi/compose.oast.yaml",
            "-f",
            "tests/integration/oast-workshop-owner.compose.yaml",
            *args,
        )

    def attach_workshop(self) -> None:
        """Recria somente o workshop usando o overlay e captura seu identificador."""
        before = self.cleanup._containers(
            f"label=com.docker.compose.project={CRAPI_PROJECT}",
            "label=com.docker.compose.service=crapi-workshop",
        )
        if len(before) != 1:
            raise ValueError("workshop inicial ausente ou ambíguo")
        self.cleanup.workshop_before = set(before)
        self.cleanup.workshop_intended = True
        self.crapi_compose(
            "up", "-d", "--no-deps", "--force-recreate", "--pull", "never", "crapi-workshop"
        )
        container = self.crapi_compose("ps", "-q", "crapi-workshop")
        assert re.fullmatch(r"[0-9a-f]{12,64}", container)
        self.client = self.docker("container", "inspect", "--format", "{{.Id}}", container)
        assert re.fullmatch(r"[0-9a-f]{64}", self.client)

    def inspect_json(self, kind: str, name: str, expression: str) -> object:
        """Lê apenas o campo de rede requerido, nunca o ambiente do contêiner."""
        return json.loads(self.docker(kind, "inspect", "--format", expression, name))

    def topology(self, *, workshop: bool = False) -> None:
        """Confere redes internas, ausência de publicação e isolamento do ZAP."""
        zap = self.compose("ps", "-q", "zap")
        gateway = self.compose("ps", "-q", "oast-gateway")
        assert zap
        assert gateway
        zap_networks = self.inspect_json("container", zap, "{{json .NetworkSettings.Networks}}")
        gateway_networks = self.inspect_json(
            "container", gateway, "{{json .NetworkSettings.Networks}}"
        )
        client_networks = self.inspect_json(
            "container", self.client, "{{json .NetworkSettings.Networks}}"
        )
        assert isinstance(zap_networks, dict)
        assert set(zap_networks) == {PROJECT + "_zap_net"}
        assert isinstance(gateway_networks, dict)
        assert set(gateway_networks) == {
            PROJECT + "_zap_net",
            self.network,
        }
        assert isinstance(client_networks, dict)
        expected = {self.network}
        if workshop:
            expected.add(CRAPI_PROJECT + "_crapi_net")
        assert set(client_networks) == expected
        for network in (PROJECT + "_zap_net", *expected):
            assert self.inspect_json("network", network, "{{json .Internal}}") is True
        assert not self.inspect_json("container", gateway, "{{json .HostConfig.PortBindings}}")
        assert not self.inspect_json("container", self.client, "{{json .HostConfig.PortBindings}}")

    def interaction_count(self) -> int:
        """Lê o contador do próprio serviço Callback no ZAP."""
        result = self.api("stats/view/stats", keyPrefix="stats.oast.callback.interactions")
        stats = result.get("stats")
        assert isinstance(stats, dict), result
        return int(str(stats.get("stats.oast.callback.interactions", 0)))

    def has_event(self, marker: str) -> bool:
        """Encontra a mensagem OAST persistida na sessão do ZAP (tipo 22)."""
        result = self.api("core/view/messages", start="0", count="10000")
        messages = result.get("messages")
        assert isinstance(messages, list), result
        return any(
            isinstance(message, dict)
            and str(message.get("type")) == "22"
            and f"/{marker} " in str(message.get("requestHeader", ""))
            for message in messages
        )

    def invoke(self, marker: str) -> None:
        """Envia somente ao Callback, a partir do emissor sintético."""
        if not re.fullmatch(r"lab-[0-9a-f]{12}", marker):
            raise ValueError("marcador de prova inválido")
        code = (
            "import urllib.request as u; o=u.build_opener(u.ProxyHandler({})); "
            f"r=o.open('http://oast-gateway:8090/{marker}', timeout=5); assert r.status == 200"
        )
        self.docker("exec", self.client, "python3", "-c", code)

    def assert_no_external_route(self) -> None:
        """TEST-NET-1 não hospeda serviço; conexão deve falhar a partir do emissor."""
        code = (
            "import errno,socket; s=socket.socket(); s.settimeout(3); "
            "result=s.connect_ex(('192.0.2.1', 443)); "
            "assert result == errno.ENETUNREACH, result"
        )
        self.docker("exec", self.client, "python3", "-c", code)

    def close(self) -> CleanupResult:
        """Encerra exclusivamente o contêiner e a ponte criados nesta prova."""
        return self.cleanup.close()

    def finish(self) -> CleanupResult:
        """Tenta limpeza e stack down, exige código zero e verifica sobras."""
        result = self.close()
        if self.stack_intended:
            self.cleanup._attempt(
                "projeto_propriedade", self.cleanup.verify_projects_owned, ownership=True
            )
            if result.unsafe:
                result.errors.append("stack_down_recusado_propriedade")
                result.errors.append("intervencao_humana_necessaria")
            else:
                self.cleanup._attempt("stack_down", self._stack_down)
            self.cleanup.verify_final()
        return result

    def _stack_down(self) -> None:
        result = self.cli.run("stack", "down", timeout=240)
        if result.code != 0:
            raise ValueError("stack down retornou código não zero")


def install_vampi(cli: LabCli, profile: Path, openapi: Path) -> None:
    """Instala apenas o perfil descartável necessário para subir a pilha via CLI."""
    cli.install_product("vampi", profile, (openapi,))
