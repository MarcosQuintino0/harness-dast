"""Limites da verificação CORS exercitados pelo caso de uso completo."""

from harness_dast.application.authz.service import Authz, AuthzRequest
from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.probe_ports import InMemorySpecs, reply
from tests.fakes.rig import Rig, agenda_profile, default_handler
from tests.fakes.scan_ports import InMemoryRunArtifacts


def test_limite_zero_nao_envia_cors_mesmo_com_get_provado() -> None:
    rig = Rig(profile=agenda_profile(authz={"cors_max_requests": 0}))
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

    assert not any(r.operation_id.startswith("authz:cors:") for r in rig.target.requests)
    assert not result.findings


def test_teto_cors_conta_as_tentativas_apos_401() -> None:
    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id.startswith("authz:cors:"):
            return reply(401, {})
        response = default_handler(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig = Rig(profile=agenda_profile(authz={"cors_max_requests": 1}), handler=handler)
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
    service.execute(
        AuthzRequest(product=rig.profile.product, run_id=probe.run_id, checks=("cors",))
    )

    sent = [r for r in rig.target.requests if r.operation_id.startswith("authz:cors:")]
    assert len(sent) <= 1
