"""Verificação CORS usando portas e alvo sintéticos em memória."""

from harness_dast.application.authz import Authz, AuthzRequest
from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.probe_ports import InMemorySpecs
from tests.fakes.rig import Rig, default_handler
from tests.fakes.scan_ports import InMemoryRunArtifacts


def test_reflexao_gera_um_achado_e_respeita_teto() -> None:
    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        response = default_handler(request, jar)
        assert isinstance(response, HttpResponse)
        origin = dict(request.headers).get("Origin")
        return response.model_copy(
            update={"cors_allow_origin": origin, "cors_allow_credentials": "true"}
        )

    rig = Rig(handler=handler)
    probe = rig.probe().execute(ProbeRequest(product=rig.profile.product))
    service = Authz(
        profiles=rig.profiles,
        specs=InMemorySpecs(rig.spec),
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        store=rig.store,
        artifacts=InMemoryRunArtifacts(rig.store),
        clock=rig.clock,
        sleeper=rig.clock,
    )
    result = service.execute(
        AuthzRequest(product=rig.profile.product, run_id=probe.run_id, checks=("cors",))
    )
    sent = [
        request for request in rig.target.requests if request.operation_id.startswith("authz:cors:")
    ]
    assert 0 < len(sent) <= 5
    assert all(request.method == "GET" for request in sent)
    assert all(dict(request.headers)["Origin"].endswith(".invalid") for request in sent)
    assert len(result.findings) == 1
    assert result.findings[0].proposed_severity == "high"
