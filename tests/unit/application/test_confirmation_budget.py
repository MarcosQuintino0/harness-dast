"""O teto por achado inclui recuos, login e as duas buscas CSRF."""

from pathlib import Path

import pytest

from harness_dast.application.confirmation import ConfirmationRequest
from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.errors import ConfigError
from tests.fakes.confirmation_budget import RetryingSessionTarget
from tests.fakes.confirmation_rig import ConfirmationRig
from tests.fakes.probe_ports import FakeTarget


def test_bloqueia_decimo_terceiro_pedido_quando_sessao_consumiu_doze(tmp_path: Path) -> None:
    rig = ConfirmationRig(tmp_path)
    profile = rig.rig.profile
    auth = profile.auth.model_copy(update={"csrf": CsrfConfig(fetch_path="/api/csrf")})
    rig.rig.profiles.add(profile.model_copy(update={"auth": auth}))
    target = FakeTarget(RetryingSessionTarget())
    rig.rig.target = target
    service = rig.service()

    with pytest.raises(ConfigError, match="interrompida"):
        service.execute(ConfirmationRequest(product="agenda", run_id=rig.run_id))

    assert len(target.requests) == 12
    assert all(not item.operation_id.startswith("confirm:") for item in target.requests)
    assert service.traffic == (0, 12)
    assert rig.store.read().entries[0].level == "inconclusive"
