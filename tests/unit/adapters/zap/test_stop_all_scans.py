"""`stop_all_scans` contra um ZAP falso com as formas reais de `ascan/view/scans` (2.17.0)."""

import json

import pytest

from harness_dast.adapters.zap.api_client import ZapApiClient
from harness_dast.domain.errors import ExternalToolError
from tests.fakes.local_server import Received, Reply, free_port, serve


def reply(payload: object) -> Reply:
    return Reply(200, json.dumps(payload).encode(), [("Content-Type", "application/json")])


class FakeZap:
    def __init__(self, scans: object) -> None:
        self.scans = scans
        self.stopped = False

    def __call__(self, r: Received) -> Reply:
        if r.path == "/JSON/ascan/view/scans/":
            return reply({"scans": self.scans})
        if r.path == "/JSON/ascan/action/stopAllScans/":
            self.stopped = True
            return reply({"Result": "OK"})
        return reply({"code": "bad_action"})


def test_stop_all_scans_conta_so_as_varreduras_em_andamento_e_manda_parar() -> None:
    zap = FakeZap(
        [
            {"id": "0", "progress": "100", "state": "FINISHED"},
            {"id": "1", "progress": "40", "state": "RUNNING"},
            {"id": "2", "progress": "10", "state": "PAUSED"},
        ]
    )

    with serve(zap) as server:
        count = ZapApiClient(server.base_url, None, timeout_seconds=2.0).stop_all_scans()

    assert count == 2
    assert zap.stopped is True


def test_stop_all_scans_recusa_resposta_com_forma_inesperada() -> None:
    with serve(FakeZap({"nao": "e lista"})) as server:
        client = ZapApiClient(server.base_url, None, timeout_seconds=2.0)
        with pytest.raises(ExternalToolError, match="inesperada"):
            client.stop_all_scans()


def test_stop_all_scans_com_zap_fora_do_ar_levanta_erro_de_ferramenta() -> None:
    client = ZapApiClient(f"http://127.0.0.1:{free_port()}", None, timeout_seconds=1.0)

    with pytest.raises(ExternalToolError, match="ZAP"):
        client.stop_all_scans()
