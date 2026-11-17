"""Apoio exclusivo à prova de Callback com emissor sintético em rede interna."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import httpx

from tests.integration.lab_support import REPO, LabCli

PYTHON_IMAGE = (
    "python:3.13-slim-bookworm@sha256:"
    "a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72"
)
PROJECT = "hdast-codex"


class OastLab:
    """Controla somente o overlay e o contêiner efêmero próprios da prova."""

    def __init__(self, cli: LabCli, key: str, nonce: str) -> None:
        self.cli = cli
        self.key = key
        self.network = f"hdast-oast-{nonce}"
        self.client = f"hdast-oast-client-{nonce}"
        self.cli.env["HDAST_OAST_NETWORK"] = self.network
        self._client_created = False
        self._overlay_started = False

    def docker(self, *args: str) -> str:
        """Executa comando explícito de suporte Docker, com timeout."""
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
            "compose", "-p", PROJECT, "-f", "compose.yaml", "-f", "lab/oast/compose.yaml", *args
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

    def start(self) -> None:
        """Cria o gateway sem recriar nem adicionar redes ao ZAP."""
        self._overlay_started = True
        self.compose("up", "-d", "--no-deps", "oast-gateway")
        self.docker(
            "run",
            "-d",
            "--pull=never",
            "--name",
            self.client,
            "--network",
            self.network,
            "--entrypoint",
            "python",
            PYTHON_IMAGE,
            "-c",
            "import time; time.sleep(300)",
        )
        self._client_created = True
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
        for suffix in ("zap_net", "lab_net", "egress_net", "host_net"):
            assert not self.docker("network", "ls", "-q", "--filter", f"name=^{PROJECT}_{suffix}$")

    def inspect_json(self, kind: str, name: str, expression: str) -> object:
        """Lê apenas o campo de rede requerido, nunca o ambiente do contêiner."""
        return json.loads(self.docker(kind, "inspect", "--format", expression, name))

    def topology(self) -> None:
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
        assert set(client_networks) == {self.network}
        for network in (PROJECT + "_zap_net", self.network):
            assert self.inspect_json("network", network, "{{json .Internal}}") is True
        assert not self.inspect_json("container", gateway, "{{json .HostConfig.PortBindings}}")

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
        self.docker("exec", self.client, "python", "-c", code)

    def assert_no_external_route(self) -> None:
        """TEST-NET-1 não hospeda serviço; conexão deve falhar a partir do emissor."""
        code = (
            "import errno,socket; s=socket.socket(); s.settimeout(3); "
            "result=s.connect_ex(('192.0.2.1', 443)); "
            "assert result == errno.ENETUNREACH, result"
        )
        self.docker("exec", self.client, "python", "-c", code)

    def close(self) -> None:
        """Encerra exclusivamente o contêiner e a ponte criados nesta prova."""
        if self._client_created:
            self.docker("stop", "-t", "1", self.client)
            self.docker("rm", self.client)
        if self._overlay_started:
            self.compose("stop", "oast-gateway")
            self.compose("rm", "-f", "oast-gateway")
            self.docker("network", "rm", self.network)


def install_vampi(cli: LabCli, profile: Path, openapi: Path) -> None:
    """Instala apenas o perfil descartável necessário para subir a pilha via CLI."""
    cli.install_product("vampi", profile, (openapi,))
