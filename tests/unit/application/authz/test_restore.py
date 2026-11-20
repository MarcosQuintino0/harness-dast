"""`authz`: parada depois do PUT de atribuição em massa nunca esconde alteração no alvo."""

from typing import Any

import pytest

from harness_dast.application.authz import checks_mass as authz_checks_mass
from harness_dast.application.authz import restore as authz_restore
from harness_dast.application.authz.service import Authz, AuthzRequest
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.errors import ExternalToolError
from tests.fakes.authz.rig import AuthzRig, Clinic


class WindowClosesAfterPut:
    """Trava que passa a valer assim que um PUT do authz chegou ao alvo."""

    def __init__(self, rig: AuthzRig) -> None:
        self._rig = rig

    def engaged(self) -> bool:
        return any(
            r.method == "PUT" and r.operation_id.startswith("authz:")
            for r in self._rig.target.requests
        )


def run_with_switch(rig: AuthzRig, switch: Any) -> AuthzResult:
    probe = rig.run_probe()
    stage = Authz(
        profiles=rig.profiles,
        specs=rig._specs(),
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        store=rig.store,
        artifacts=rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
        kill_switch=switch,
    )
    return stage.execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )


def unrestored(result: AuthzResult) -> list[Any]:
    return [n for n in result.not_tested if n.reason == "possible_unrestored_change"]


def test_a_window_closing_right_after_the_put_is_reported_as_possible_unrestored_change() -> None:
    rig = AuthzRig(Clinic(mass=True))

    result = run_with_switch(rig, WindowClosesAfterPut(rig))

    puts = [r for r in rig.target.requests if r.method == "PUT" and "authz" in r.operation_id]
    assert result.status == "stopped_window"
    assert len(puts) == 1  # a restauração não fura a janela: nada é enviado depois
    notes = unrestored(result)
    assert len(notes) == 1
    assert notes[0].operation_id == "atualizarPerfil"
    assert "pac_a" in notes[0].message


def test_an_interrupted_read_after_the_put_still_reports_the_unrestored_change() -> None:
    rig = AuthzRig(Clinic(mass=True))
    original = rig.target._handler

    def broken(request: Any, jar: Any) -> Any:
        puts = [r for r in rig.target.requests if r.operation_id.startswith("authz:")]
        late_read = request.operation_id.startswith("authz:") and request.method == "GET"
        if any(r.method == "PUT" for r in puts) and late_read:
            return ExternalToolError("O proxy do ZAP não respondeu.")
        return original(request, jar)

    rig.target._handler = broken
    probe = rig.run_probe()

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )

    assert result.status == "stopped_zap"
    assert len(unrestored(result)) == 1


def test_interrupted_restoration_does_not_exceed_write_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(authz_checks_mass, "MAX_MASS_REQUESTS", 2)
    monkeypatch.setattr(authz_restore, "MAX_MASS_REQUESTS", 2)
    rig = AuthzRig(Clinic(mass=True))
    original = rig.target._handler

    def broken(request: Any, jar: Any) -> Any:
        puts = [
            r
            for r in rig.target.requests
            if r.operation_id.startswith("authz:") and r.method == "PUT"
        ]
        if request.operation_id.startswith("authz:") and request.method == "PUT" and len(puts) >= 2:
            return ExternalToolError("O proxy do ZAP não respondeu.")
        return original(request, jar)

    rig.target._handler = broken
    probe = rig.run_probe()
    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )

    puts = [
        r for r in rig.target.requests if r.operation_id.startswith("authz:") and r.method == "PUT"
    ]
    assert len(puts) == 2
    assert unrestored(result)
