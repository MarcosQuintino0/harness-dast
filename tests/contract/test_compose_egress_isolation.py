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
