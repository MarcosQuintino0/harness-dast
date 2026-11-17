"""Contratos das consultas sanitizadas da prova de integração do crAPI."""

import json

import pytest

from tests.integration import crapi_support as support


def _docker_fixture(*args: str) -> str:
    if args[:2] == ("network", "inspect"):
        return "true"
    if args[:2] == ("volume", "ls"):
        return ""
    if args[0] == "ps":
        return "zap" if args[-1].endswith("=hdast-codex") else "workshop\nweb"
    if args[0] == "inspect":
        template, container = args[2], args[3]
        if ".Config.Labels" in template:
            service = {"zap": "zap", "workshop": "crapi-workshop", "web": "crapi-web"}[container]
            return json.dumps(service)
        if ".NetworkSettings.Networks" in template:
            network = "hdast-codex_zap_net" if container == "zap" else "hdast-crapi-codex_crapi_net"
            return json.dumps({network: {}})
        if ".NetworkSettings.Ports" in template:
            return json.dumps({"80/tcp": [{"HostIp": "127.0.0.1"}]})
        return "disposable-volume" if container == "workshop" else ""
    raise AssertionError("consulta inesperada")


def test_topologia_confere_redes_portas_e_volumes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support, "_docker", _docker_fixture)
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
            return json.dumps({"hdast-crapi-codex_publish_net": {}})
        return _docker_fixture(*args)

    monkeypatch.setattr(support, "_docker", connected)
    with pytest.raises(AssertionError):
        support.inspect_topology()


def test_metricas_nao_incluem_resposta_arbitraria(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        stdout = '{"ok": false, "error": {"code": "STACK_STALE", "message": "secret"}}'
        stderr = "secret"
        returncode = 4

    monkeypatch.setattr(support.subprocess, "run", lambda *args, **kwargs: Completed())
    cli = support.LabCli.__new__(support.LabCli)
    cli.env = {}
    _, metrics = support.run_cli(cli, "preflight", "crapi")
    assert metrics["error_code"] == "STACK_STALE"
    assert "secret" not in json.dumps(metrics)
