"""Contratos das consultas sanitizadas da prova de integração do crAPI."""

import json
import subprocess
from functools import partial
from pathlib import Path

import pytest

from tests.integration import crapi_support as support
from tests.integration.lab_support import LabCli


def _docker_fixture(*args: str, suffix: str = "") -> str:
    if args[:2] == ("network", "inspect"):
        return "true"
    if args[:2] == ("volume", "ls"):
        return ""
    if args[0] == "ps":
        projects = {f"hdast{suffix}": "zap", f"hdast-crapi{suffix}": "workshop\nweb"}
        return projects[args[-1].rsplit("=", 1)[1]]
    if args[0] == "inspect":
        template, container = args[2], args[3]
        if ".Config.Labels" in template:
            service = {"zap": "zap", "workshop": "crapi-workshop", "web": "crapi-web"}[container]
            return json.dumps(service)
        if ".NetworkSettings.Networks" in template:
            network = (
                f"hdast{suffix}_zap_net" if container == "zap" else f"hdast-crapi{suffix}_crapi_net"
            )
            return json.dumps({network: {}})
        if ".NetworkSettings.Ports" in template:
            return json.dumps({"80/tcp": [{"HostIp": "127.0.0.1"}]})
        return "disposable-volume" if container == "workshop" else ""
    raise AssertionError("consulta inesperada")


@pytest.mark.parametrize("suffix", ["", "-codex", "-claude"])
def test_topologia_confere_redes_portas_e_volumes(
    monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    monkeypatch.setenv("HDAST_IT_STACK_SUFFIX", suffix)
    monkeypatch.setattr(support, "_docker", partial(_docker_fixture, suffix=suffix))
    volumes = support.inspect_topology()
    assert volumes == {"disposable-volume"}
    support.assert_volumes_removed(volumes)


def test_rejeita_porta_publicada_em_todas_as_interfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    def exposed(*args: str) -> str:
        if args[0] == "inspect" and ".NetworkSettings.Ports" in args[2]:
            return json.dumps({"80/tcp": [{"HostIp": "0.0.0.0"}]})  # noqa: S104 - dado falso
        return _docker_fixture(*args)

    monkeypatch.setattr(support, "_docker", exposed)
    with pytest.raises(AssertionError):
        support.inspect_topology()


def test_rejeita_volume_que_sobrou(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support, "_docker", lambda *args: "disposable-volume")
    with pytest.raises(AssertionError):
        support.assert_volumes_removed({"disposable-volume"})


def test_rejeita_zap_na_rede_publicada_do_alvo(monkeypatch: pytest.MonkeyPatch) -> None:
    def connected(*args: str) -> str:
        if (
            args[0] == "inspect"
            and ".NetworkSettings.Networks" in args[2]
            and args[3] in {"zap", "web"}
        ):
            return json.dumps({"hdast-crapi_publish_net": {}})
        return _docker_fixture(*args)

    monkeypatch.setattr(support, "_docker", connected)
    with pytest.raises(AssertionError):
        support.inspect_topology()


def test_metricas_nao_incluem_resposta_arbitraria(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        stdout = '{"ok": false, "error": {"code": "STACK_STALE", "message": "secret"}}'
        stderr = "secret"
        returncode = 4

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Completed())
    cli = LabCli.__new__(LabCli)
    cli.env = {}
    _, metrics = support.run_cli(cli, "preflight", "crapi")
    assert metrics["error_code"] == "STACK_STALE"
    assert "secret" not in json.dumps(metrics)


@pytest.mark.parametrize("suffix", [None, "-codex", "-claude"])
def test_nomes_de_projeto_correspondem_ao_sufixo_da_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str | None
) -> None:
    if suffix is not None:
        monkeypatch.setenv("HDAST_IT_STACK_SUFFIX", suffix)
    cli = LabCli(tmp_path, {})

    applied = cli.env.get("HDAST_STACK_PROJECT_SUFFIX", "")
    assert applied == (suffix or "")
    assert (support.project(), support.crapi_project()) == (
        f"hdast{applied}",
        f"hdast-crapi{applied}",
    )
