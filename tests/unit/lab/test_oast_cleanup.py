"""Falhas parciais e propriedade na limpeza da prova OAST, sem Docker.

O falso com estado e os cenários ficam juntos para exercitar a mesma fronteira Docker em
falhas de criação, inspeção, remoção e conferência final, sem compartilhamento de estado.
"""

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
import yaml

from tests.integration.lab_support import REPO, CliResult, LabCli
from tests.integration.oast_cleanup import CRAPI_PROJECT, PROJECT
from tests.integration.oast_support import OastLab
from tests.integration.test_lab_oast import finish_proof

OWNER = "a" * 12
NETWORK = "b" * 64
CLIENT = "c" * 64
GATEWAY = "d" * 64
WORKSHOP = "e" * 64
ORIGINAL_WORKSHOP = "f" * 64
FOREIGN = "1" * 64


class FakeCli:
    def __init__(self, down_code: int = 0) -> None:
        self.env: dict[str, str] = {}
        self.down_code = down_code
        self.calls: list[tuple[str, ...]] = []

    def run(self, *args: str, timeout: int = 0) -> CliResult:
        self.calls.append(args)
        if self.down_code == -1:
            raise subprocess.TimeoutExpired("stack", 1)
        return CliResult(self.down_code, {}, "credential-not-for-evidence", "")


class FakeDocker:
    """Executa operações por estado e injeta falhas antes ou depois da mutação."""

    def __init__(self) -> None:
        self.network = False
        self.foreign_network = False
        self.foreign_named_network = False
        self.volumes: list[str] = []
        self.network_owner = OWNER
        self.containers: dict[str, dict[str, str]] = {}
        self.members: set[str] = set()
        self.fail: set[str] = set()
        self.calls: list[tuple[str, ...]] = []

    def add(self, ident: str, name: str, project: str, service: str, owner: str = OWNER) -> None:
        self.containers[ident] = {
            "name": name,
            "project": project,
            "service": service,
            "owner": owner,
        }

    def _failure(self, name: str) -> None:
        if name in self.fail:
            raise subprocess.TimeoutExpired(name, 1)

    def __call__(self, args: tuple[str, ...]) -> str:
        self.calls.append(args)
        if args[0] == "compose":
            return self._compose(args)
        if args[0] == "run":
            self.add(CLIENT, "hdast-oast-client-" + OWNER, "", "", OWNER)
            self.members.add(CLIENT)
            self._failure("run_after_create")
            return CLIENT
        if args[0] == "ps":
            return self._ps(args)
        if args[:2] == ("container", "inspect"):
            return self._inspect_container(args)
        if args[0] == "network":
            return self._network(args)
        if args[0] in {"stop", "rm"}:
            return self._remove(args)
        if args[:2] == ("volume", "ls"):
            return "\n".join(self.volumes)
        raise AssertionError(f"comando não previsto: {args}")

    def _network(self, args: tuple[str, ...]) -> str:
        if args[1] == "ls":
            if self.foreign_network and args[-1] == f"label=com.docker.compose.project={PROJECT}":
                return FOREIGN
            if self.foreign_named_network and args[-1] == f"name=^{PROJECT}_lab_net$":
                return FOREIGN
            own_filters = {
                f"name=^hdast-oast-{OWNER}$",
                f"label=com.docker.compose.project={PROJECT}",
            }
            return NETWORK if self.network and args[-1] in own_filters else ""
        if args[1] == "inspect":
            if "com.docker.compose.project" in args[3]:
                return PROJECT
            return (
                json.dumps({key: {} for key in self.members})
                if "Containers" in args[3]
                else self.network_owner
            )
        if args[1] == "disconnect":
            self._failure("disconnect")
            self.members.discard(args[-1])
            return ""
        if args[1] == "rm":
            self._failure("network_rm")
            if self.members:
                raise subprocess.CalledProcessError(1, args)
            self.network = False
            return ""
        raise AssertionError(f"rede inesperada: {args}")

    def _compose(self, args: tuple[str, ...]) -> str:
        if "up" in args and "oast-gateway" in args:
            self.network = True
            self.add(GATEWAY, "gateway", PROJECT, "oast-gateway")
            self.members.add(GATEWAY)
            self._failure("gateway_after_create")
            return ""
        if "up" in args and "crapi-workshop" in args:
            self.containers.pop(ORIGINAL_WORKSHOP, None)
            self.add(WORKSHOP, "workshop", CRAPI_PROJECT, "crapi-workshop")
            self.members.add(WORKSHOP)
            return ""
        if "ps" in args:
            self._failure("compose_ps")
            return WORKSHOP
        raise AssertionError("compose inesperado")

    def _ps(self, args: tuple[str, ...]) -> str:
        filters = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "--filter"]
        if any("service=oast-gateway" in value for value in filters):
            self._failure("gateway_lookup")
        if any("service=crapi-workshop" in value for value in filters):
            self._failure("workshop_lookup")
        if any(value.startswith("name=^/") for value in filters):
            self._failure("client_lookup")
        found = []
        for ident, item in self.containers.items():
            if all(self._matches(item, value) for value in filters):
                found.append(ident)
        return "\n".join(found)

    @staticmethod
    def _matches(item: dict[str, str], value: str) -> bool:
        if value.startswith("name=^/"):
            return item["name"] == value.removeprefix("name=^/").removesuffix("$")
        if value.startswith("label=com.docker.compose.project="):
            return item["project"] == value.split("=", 2)[2]
        if value.startswith("label=com.docker.compose.service="):
            return item["service"] == value.split("=", 2)[2]
        raise AssertionError("filtro inesperado")

    def _inspect_container(self, args: tuple[str, ...]) -> str:
        ident = args[-1]
        if args[3] == "{{.Id}}":
            self._failure("container_id")
            return ident
        item = self.containers[ident]
        return item["owner"] if "io.hdast.oast.owner" in args[3] else item["service"]

    def _remove(self, args: tuple[str, ...]) -> str:
        ident = args[-1]
        role = "client" if ident == CLIENT else "gateway"
        self._failure(role + "_" + args[0])
        if args[0] == "rm":
            self.containers.pop(ident)
            self.members.discard(ident)
        return ""


def make_lab(docker: FakeDocker, cli: FakeCli | None = None) -> OastLab:
    # O dublê implementa a fronteira utilizada; nenhuma chamada chega ao processo real.
    return OastLab(cast(LabCli, cli or FakeCli()), "key-for-test", OWNER, docker)


def test_reconcilia_cliente_quando_run_expira_apos_criar() -> None:
    docker = FakeDocker()
    docker.fail.add("run_after_create")
    lab = make_lab(docker)
    with pytest.raises(subprocess.TimeoutExpired):
        lab.start()
    result = lab.close()
    assert result.errors == []
    assert CLIENT not in docker.containers
    assert GATEWAY not in docker.containers
    assert not docker.network


def test_overlays_identificam_rede_gateway_e_workshop() -> None:
    root = yaml.safe_load(
        (REPO / "tests/integration/oast-owner.compose.yaml").read_text(encoding="utf-8")
    )
    target = yaml.safe_load(
        (REPO / "tests/integration/oast-workshop-owner.compose.yaml").read_text(encoding="utf-8")
    )
    expected = "${HDAST_OAST_OWNER:?Identificador da prova obrigatório}"
    assert root["services"]["oast-gateway"]["labels"]["io.hdast.oast.owner"] == expected
    assert root["networks"]["oast_net"]["labels"]["io.hdast.oast.owner"] == expected
    assert target["services"]["crapi-workshop"]["labels"]["io.hdast.oast.owner"] == expected


def test_reconcilia_gateway_quando_compose_expira_apos_criar() -> None:
    docker = FakeDocker()
    docker.fail.add("gateway_after_create")
    lab = make_lab(docker)
    with pytest.raises(subprocess.TimeoutExpired):
        lab.start()
    result = lab.close()
    assert result.errors == []
    assert GATEWAY not in docker.containers
    assert not docker.network


@pytest.mark.parametrize("failure", ["compose_ps", "container_id"])
def test_reconcilia_workshop_quando_consulta_falha_apos_anexar(failure: str) -> None:
    docker = FakeDocker()
    docker.network = True
    docker.add(ORIGINAL_WORKSHOP, "workshop", CRAPI_PROJECT, "crapi-workshop", "")
    docker.fail.add(failure)
    lab = make_lab(docker)
    lab.cleanup.gateway_intended = True
    with pytest.raises(subprocess.TimeoutExpired):
        lab.attach_workshop()
    result = lab.close()
    assert result.errors == []
    assert WORKSHOP not in docker.members
    assert not docker.network


@pytest.mark.parametrize(
    "failure",
    ["disconnect", "client_stop", "client_rm", "gateway_stop", "gateway_rm", "network_rm"],
)
def test_cada_falha_permite_tentar_as_demais_etapas(failure: str) -> None:
    docker = FakeDocker()
    docker.network = True
    docker.add(CLIENT, "hdast-oast-client-" + OWNER, "", "")
    docker.add(GATEWAY, "gateway", PROJECT, "oast-gateway")
    docker.add(WORKSHOP, "workshop", CRAPI_PROJECT, "crapi-workshop")
    docker.members = {CLIENT, GATEWAY, WORKSHOP}
    docker.fail.add(failure)
    lab = make_lab(docker)
    lab.cleanup.client_intended = lab.cleanup.gateway_intended = lab.cleanup.workshop_intended = (
        True
    )
    result = lab.close()
    assert result.errors
    assert ("network", "disconnect", NETWORK, WORKSHOP) in docker.calls
    assert ("stop", "-t", "1", CLIENT) in docker.calls
    assert ("rm", CLIENT) in docker.calls
    assert ("stop", "-t", "1", GATEWAY) in docker.calls
    assert ("rm", GATEWAY) in docker.calls
    assert ("network", "rm", NETWORK) in docker.calls


def test_recusa_recursos_alheios_sem_remove_los() -> None:
    docker = FakeDocker()
    docker.network = True
    docker.add(CLIENT, "hdast-oast-client-" + OWNER, "", "", "outro")
    docker.add(GATEWAY, "gateway", PROJECT, "oast-gateway", "outro")
    cli = FakeCli()
    lab = make_lab(docker, cli)
    lab.cleanup.client_intended = lab.cleanup.gateway_intended = True
    lab.stack_intended = True
    result = lab.finish()
    assert result.unsafe
    assert CLIENT in docker.containers
    assert GATEWAY in docker.containers
    assert ("rm", CLIENT) not in docker.calls
    assert ("rm", GATEWAY) not in docker.calls
    assert ("stack", "down") not in cli.calls


@pytest.mark.parametrize("failure", ["client_lookup", "gateway_lookup", "workshop_lookup"])
def test_falha_de_consulta_nao_interrompe_outras_etapas(failure: str) -> None:
    docker = FakeDocker()
    docker.network = True
    docker.add(CLIENT, "hdast-oast-client-" + OWNER, "", "")
    docker.add(GATEWAY, "gateway", PROJECT, "oast-gateway")
    docker.add(WORKSHOP, "workshop", CRAPI_PROJECT, "crapi-workshop")
    docker.members = {CLIENT, GATEWAY, WORKSHOP}
    docker.fail.add(failure)
    lab = make_lab(docker)
    lab.cleanup.client_intended = lab.cleanup.gateway_intended = lab.cleanup.workshop_intended = (
        True
    )
    result = lab.close()
    assert result.errors
    if failure != "client_lookup":
        assert ("rm", CLIENT) in docker.calls
    if failure != "gateway_lookup":
        assert ("rm", GATEWAY) in docker.calls
    if failure != "workshop_lookup":
        assert ("network", "disconnect", NETWORK, WORKSHOP) in docker.calls


def test_workshop_alheio_fora_da_rede_impede_stack_down() -> None:
    docker = FakeDocker()
    docker.add(WORKSHOP, "workshop", CRAPI_PROJECT, "crapi-workshop", "outro")
    cli = FakeCli()
    lab = make_lab(docker, cli)
    lab.cleanup.workshop_intended = True
    lab.stack_intended = True
    result = lab.finish()
    assert "stack_down_recusado_propriedade" in result.errors
    assert ("stack", "down") not in cli.calls


def test_servico_alheio_injetado_apos_snapshot_impede_stack_down() -> None:
    docker = FakeDocker()
    docker.add(FOREIGN, "outro", PROJECT, "zap", "outro")
    cli = FakeCli()
    lab = make_lab(docker, cli)
    lab.cleanup.stack_containers = set()
    lab.stack_intended = True
    result = lab.finish()
    assert "stack_down_recusado_propriedade" in result.errors
    assert ("stack", "down") not in cli.calls
    assert FOREIGN in docker.containers


@pytest.mark.parametrize("kind", ["network", "named_network", "volume"])
def test_recurso_alheio_injetado_apos_snapshot_impede_stack_down(kind: str) -> None:
    docker = FakeDocker()
    cli = FakeCli()
    lab = make_lab(docker, cli)
    lab.cleanup.capture_stack()
    if kind == "network":
        docker.foreign_network = True
    elif kind == "named_network":
        docker.foreign_named_network = True
    else:
        docker.volumes = ["foreign-volume"]
    lab.stack_intended = True
    result = lab.finish()
    assert "stack_down_recusado_propriedade" in result.errors
    assert ("stack", "down") not in cli.calls


def test_stack_down_nao_zero_faz_prova_falhar_e_grava_erro_sanitizado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker = FakeDocker()
    cli = FakeCli(down_code=1)
    lab = make_lab(docker, cli)
    lab.stack_intended = True
    monkeypatch.setenv("HDAST_IT_METRICS_DIR", str(tmp_path))
    with pytest.raises(AssertionError, match="stack_down"):
        finish_proof(lab, "lab-123456789abc", {"interaction": "confirmed"})
    evidence = (tmp_path / "oast-callback-lab-123456789abc.json").read_text(encoding="utf-8")
    assert '"status": "error"' in evidence
    assert "credential-not-for-evidence" not in evidence
    assert ("stack", "down") in cli.calls


def test_rede_alheia_nao_e_removida() -> None:
    docker = FakeDocker()
    docker.network = True
    docker.network_owner = "outro"
    lab = make_lab(docker)
    lab.cleanup.gateway_intended = True
    result = lab.close()
    assert result.unsafe
    assert docker.network
    assert ("network", "rm", NETWORK) not in docker.calls


def test_sobras_sao_reportadas_apos_stack_down_com_sucesso() -> None:
    docker = FakeDocker()
    docker.add(WORKSHOP, "workshop", CRAPI_PROJECT, "crapi-workshop")
    lab = make_lab(docker)
    lab.stack_intended = True
    result = lab.finish()
    assert CRAPI_PROJECT + "_containers_restantes" in result.errors
    assert (
        "volume",
        "ls",
        "-q",
        "--filter",
        f"label=com.docker.compose.project={CRAPI_PROJECT}",
    ) in docker.calls


def test_timeout_de_stack_down_nao_impede_verificacao_final() -> None:
    docker = FakeDocker()
    lab = make_lab(docker, FakeCli(down_code=-1))
    lab.stack_intended = True
    result = lab.finish()
    assert "stack_down" in result.errors
    assert (
        "volume",
        "ls",
        "-q",
        "--filter",
        f"label=com.docker.compose.project={CRAPI_PROJECT}",
    ) in docker.calls


def test_falha_original_recebe_nota_da_limpeza(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lab = make_lab(FakeDocker(), FakeCli(down_code=1))
    lab.stack_intended = True
    monkeypatch.setenv("HDAST_IT_METRICS_DIR", str(tmp_path))

    def fail_then_finish() -> None:
        try:
            raise ValueError("falha original")
        finally:
            finish_proof(lab, "lab-123456789abc", {"interaction": "not_confirmed"})

    with pytest.raises(ValueError, match="falha original") as captured:
        fail_then_finish()
    assert any("stack_down" in note for note in captured.value.__notes__)
