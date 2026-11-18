"""Leitura pontual do ZAP com dublê local, sem tráfego ao alvo ou Docker."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from tests.integration.lab_support import ZapView
from tests.integration.performance_resources_support import ResourceSampler
from tests.integration.zap_scan_readback_support import FastZapView, active_scans, sample_zap


class FakeZapView(ZapView):
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = iter(responses)
        self.paths: list[str] = []

    def _get(self, path: str, **params: str) -> dict[str, Any]:
        self.paths.append(path)
        return next(self.responses)


def _scan(state: str = "RUNNING", progress: str = "42", ident: str = "7") -> dict[str, Any]:
    return {"scans": [{"id": ident, "state": state, "progress": progress, "url": "nao-publicar"}]}


def test_leitura_entre_duas_consultas_ativas_preserva_so_dados_seguros() -> None:
    view = FakeZapView([_scan(), {"DelayInMs": "20"}, _scan(progress="43")])
    result = sample_zap(view)
    assert result is not None
    assert result["delay_ms"] == 20
    assert result["scans"] == [{"id": "7", "state": "RUNNING", "progress": 43}]
    assert "nao-publicar" not in str(result)
    assert result["at"].endswith("+00:00")


def test_transporte_consulta_somente_api_zap_e_nao_publica_chave(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies = iter([_scan(), {"DelayInMs": "20"}, _scan()])
    seen: list[str] = []

    def fake_get(url: str, **kwargs: Any) -> Any:
        seen.append(url)
        assert kwargs["headers"]["X-ZAP-API-KEY"] == "chave-sintetica"
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: next(bodies))

    monkeypatch.setattr(httpx, "get", fake_get)
    view = FastZapView({"zap_url": "http://127.0.0.1:1234", "zap_api_key": "chave-sintetica"})
    sample = sample_zap(view)
    assert sample is not None
    assert seen == [
        "http://127.0.0.1:1234/JSON/ascan/view/scans/",
        "http://127.0.0.1:1234/JSON/ascan/view/optionDelayInMs/",
        "http://127.0.0.1:1234/JSON/ascan/view/scans/",
    ]
    assert "chave-sintetica" not in str(sample)


def test_nenhuma_leitura_de_opcao_quando_nao_ha_scan_ativo() -> None:
    view = FakeZapView([_scan("FINISHED", "100")])
    assert sample_zap(view) is None
    assert len(view.paths) == 1


def test_scan_que_termina_durante_leitura_nao_gera_amostra() -> None:
    view = FakeZapView([_scan(), {"DelayInMs": "0"}, _scan("FINISHED", "100")])
    assert sample_zap(view) is None


def test_tempo_limite_da_api_nao_interrompe_a_varredura() -> None:
    class UnavailableZap(FakeZapView):
        def _get(self, path: str, **params: str) -> dict[str, Any]:
            raise httpx.ReadTimeout("mensagem externa que não deve ser salva")

    sampler = ResourceSampler(zap=UnavailableZap([]))
    sampler._sample_zap()
    assert sampler.zap_unavailable == 1
    assert sampler.zap_errors == {"transport": 1}
    assert sampler.zap_samples == []


@pytest.mark.parametrize("delay", [None, "", "-1", "1.5", True, "1e3"])
def test_valor_de_opcao_invalido_fica_indisponivel(delay: object) -> None:
    view = FakeZapView([_scan(), {"DelayInMs": delay}])
    sampler = ResourceSampler(zap=view)
    sampler._sample_zap()
    assert sampler.zap_unavailable == 1
    assert sampler.zap_errors == {"invalid_format": 1}
    assert sampler.zap_samples == []


def test_chave_errada_nao_confirma_atraso() -> None:
    view = FakeZapView([_scan(), {"optionDelayInMs": "20"}])
    sampler = ResourceSampler(zap=view)
    sampler._sample_zap()
    assert sampler.zap_errors == {"invalid_format": 1}
    assert sampler.zap_samples == []


def test_envelope_de_erro_da_api_fica_categorizado_sem_mensagem() -> None:
    view = FakeZapView([{"code": "bad_action", "message": "nao-publicar"}])
    sampler = ResourceSampler(zap=view)
    sampler._sample_zap()
    assert sampler.zap_errors == {"api_error": 1}
    assert "nao-publicar" not in str(sampler.zap_errors)


def test_status_http_fica_categorizado_sem_detalhes() -> None:
    class FailedZap(FakeZapView):
        def _get(self, path: str, **params: str) -> dict[str, Any]:
            response = httpx.Response(403, request=httpx.Request("GET", "http://local"))
            raise httpx.HTTPStatusError("nao-publicar", request=response.request, response=response)

    sampler = ResourceSampler(zap=FailedZap([]))
    sampler._sample_zap()
    assert sampler.zap_errors == {"http_403": 1}
    assert "nao-publicar" not in str(sampler.zap_errors)


@pytest.mark.parametrize(
    "row",
    [
        {"id": "x", "state": "RUNNING", "progress": "5"},
        {"id": "1", "state": "RUNNING", "progress": "?"},
    ],
)
def test_scan_malformado_e_recusado(row: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="scan inválido"):
        active_scans({"scans": [row]})
