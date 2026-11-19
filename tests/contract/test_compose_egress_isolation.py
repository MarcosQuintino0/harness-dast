from itertools import pairwise
from pathlib import Path
from shlex import split
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.contract
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=("compose.yaml", "src/harness_dast/compose.yaml"), ids=("clone", "wheel"))
def compose(request: pytest.FixtureRequest) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / request.param).read_text(encoding="utf-8"))
    return data


def test_zap_fica_so_na_rede_interna(compose: dict[str, Any]) -> None:
    zap = compose["services"]["zap"]

    assert set(zap["networks"]) == {"zap_net"}
    assert compose["networks"]["zap_net"]["internal"] is True
    assert "network_mode" not in zap


def test_zap_usa_exclusivamente_a_cerca_original(compose: dict[str, Any]) -> None:
    zap = compose["services"]["zap"]
    arguments = split(zap["command"][-1])
    proxy_options = [
        value
        for option, value in pairwise(arguments)
        if option == "-config" and value.startswith("network.connection.httpProxy.")
    ]

    assert sorted(proxy_options) == [
        "network.connection.httpProxy.enabled=true",
        "network.connection.httpProxy.host=scope-proxy",
        "network.connection.httpProxy.port=3128",
    ]
    assert zap["depends_on"] == {"scope-proxy": {"condition": "service_healthy"}}
    assert "scope-proxy-nuclei" not in yaml.safe_dump(zap)


def _by_target(volumes: list[str]) -> dict[str, str]:
    # O destino vem depois de "}:", porque o valor padrão da variável também tem ":".
    return {volume.split("}:", 1)[1].split(":")[0]: volume for volume in volumes}


def test_nuclei_fica_so_na_rede_interna_e_sobe_so_por_perfil(compose: dict[str, Any]) -> None:
    nuclei = compose["services"]["nuclei"]

    assert list(nuclei["networks"]) == ["zap_net"]
    assert "network_mode" not in nuclei
    assert "ports" not in nuclei
    assert nuclei["profiles"] == ["nuclei"]
    assert compose["networks"]["zap_net"]["internal"] is True


def test_nuclei_nao_leva_segredo_no_ambiente_nem_volume_do_host(compose: dict[str, Any]) -> None:
    nuclei = compose["services"]["nuclei"]

    assert "environment" not in nuclei
    assert "env_file" not in nuclei
    assert "volumes" not in nuclei
    assert nuclei.get("stdin_open", False) is False
    assert nuclei.get("tty", False) is False


def test_nuclei_tem_o_endurecimento_da_cerca_e_imagem_so_local(compose: dict[str, Any]) -> None:
    nuclei = compose["services"]["nuclei"]

    assert nuclei["cap_drop"] == ["ALL"]
    assert nuclei["read_only"] is True
    assert nuclei["security_opt"] == ["no-new-privileges:true"]
    assert nuclei["user"] == "10002:10002"
    assert nuclei["pull_policy"] == "never"
    assert nuclei["image"].startswith("${HDAST_NUCLEI_IMAGE:-")
    assert nuclei["mem_limit"]
    assert nuclei["pids_limit"]
    assert all("uid=10002" in mount for mount in nuclei["tmpfs"])


def test_cerca_do_nuclei_usa_a_mesma_imagem_e_tem_pasta_propria(compose: dict[str, Any]) -> None:
    original = compose["services"]["scope-proxy"]
    fence = compose["services"]["scope-proxy-nuclei"]

    assert fence["image"] == original["image"]
    assert "profiles" not in fence
    assert set(fence["networks"]) == {"zap_net", "lab_net", "egress_net"}
    mounts = _by_target(fence["volumes"])
    original_mounts = _by_target(original["volumes"])
    assert "HDAST_NUCLEI_POLICY_DIR" in mounts["/policy"]
    assert "HDAST_NUCLEI_AUDIT_DIR" in mounts["/audit"]
    assert mounts["/policy"] != original_mounts["/policy"]
    assert mounts["/audit"] != original_mounts["/audit"]
    assert mounts["/policy"].endswith(":ro")


def test_cerca_do_nuclei_tem_os_mesmos_endurecimentos_da_original(
    compose: dict[str, Any],
) -> None:
    original = compose["services"]["scope-proxy"]
    fence = compose["services"]["scope-proxy-nuclei"]

    for key in (
        "user",
        "init",
        "cap_drop",
        "read_only",
        "security_opt",
        "mem_limit",
        "pids_limit",
        "tmpfs",
        "restart",
        "pull_policy",
        "healthcheck",
        "environment",
    ):
        assert fence[key] == original[key], key


def test_so_o_nuclei_referencia_a_cerca_do_nuclei(compose: dict[str, Any]) -> None:
    referencing = {
        name
        for name, service in compose["services"].items()
        if name != "scope-proxy-nuclei" and "scope-proxy-nuclei" in yaml.safe_dump(service)
    }

    assert referencing == {"nuclei"}
    assert compose["services"]["nuclei"]["depends_on"] == {
        "scope-proxy-nuclei": {"condition": "service_healthy"}
    }


def test_nenhum_servico_alem_do_nuclei_usa_a_pasta_de_politica_do_nuclei(
    compose: dict[str, Any],
) -> None:
    users = {
        name
        for name, service in compose["services"].items()
        if "HDAST_NUCLEI_POLICY_DIR" in yaml.safe_dump(service)
    }

    assert users == {"scope-proxy-nuclei"}
