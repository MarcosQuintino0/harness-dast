"""`authz`: atribuição em massa com campos derivados do OpenAPI em `PUT` (ADR 0040)."""

from typing import Any

import pytest

from harness_dast.application import authz_checks_mass
from harness_dast.application.authz import Authz, AuthzRequest
from harness_dast.domain.authz_result import AuthzNotTested, AuthzResult
from tests.fakes.authz_rig import AuthzRig, Clinic, clinic_spec

PUT_ONLY: dict[str, Any] = {"mass_assignment_methods": ["PUT"]}


def derived_rig(clinic: Clinic, **authz: Any) -> AuthzRig:
    return AuthzRig(clinic, spec=clinic_spec(derived=True), authz={**PUT_ONLY, **authz})


def run_mass(rig: AuthzRig) -> AuthzResult:
    probe = rig.run_probe()
    return rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )


def notes(result: AuthzResult, reason: str) -> list[AuthzNotTested]:
    return [n for n in result.not_tested if n.reason == reason]


def authz_puts(rig: AuthzRig) -> list[bytes]:
    return [
        r.body or b""
        for r in rig.target.requests
        if r.method == "PUT" and r.operation_id.startswith("authz:")
    ]


def test_a_response_only_field_accepted_by_the_server_becomes_a_finding_and_is_restored() -> None:
    rig = derived_rig(Clinic(stores=("nivelAcesso", "saldo")))

    result = run_mass(rig)

    found = {f.fields[0]: f for f in result.findings}
    assert set(found) == {"nivelAcesso", "saldo"}
    assert found["nivelAcesso"].candidate_source == "response_only"
    assert found["nivelAcesso"].proposed_severity == "high"
    assert found["saldo"].proposed_severity == "high"
    assert "valor anterior foi restaurado" in found["saldo"].evidence
    assert rig.clinic.extra["pac_a"] == {"nivelAcesso": "basico", "saldo": 10}
    assert any(
        effect.write_operation == "atualizarPerfil"
        and effect.read_operation == "obterPerfil"
        and effect.account == "pac_a"
        and effect.fields == ("saldo",)
        for effect in result.effects
    )


def test_a_derived_field_the_server_ignores_is_tested_without_a_finding() -> None:
    rig = derived_rig(Clinic())

    result = run_mass(rig)

    assert result.findings == ()
    sent = b"".join(authz_puts(rig))
    assert b"nivelAcesso" in sent
    assert b"saldo" in sent


def test_the_test_value_follows_the_type_and_the_current_value() -> None:
    rig = derived_rig(Clinic(stores=("nivelAcesso", "saldo")))

    run_mass(rig)

    sent = b"".join(authz_puts(rig))
    assert b'"nivelAcesso":"admin"' in sent
    assert b'"saldo":11' in sent


def test_declared_fields_come_first_and_win_over_the_derived_one_with_the_same_name() -> None:
    rig = derived_rig(
        Clinic(stores=("nivelAcesso",)),
        mass_assignment_fields=[{"name": "nivel_acesso", "value": "dono"}],
    )

    result = run_mass(rig)

    sent = authz_puts(rig)
    assert b'"nivel_acesso":"dono"' in b"".join(sent)
    assert b'"nivelAcesso":"admin"' not in b"".join(sent)
    assert [f.fields[0] for f in result.findings] == []


def test_turning_derivation_off_goes_back_to_the_declared_fields_only() -> None:
    rig = derived_rig(Clinic(stores=("nivelAcesso", "saldo")), derive_mass_candidates=False)

    result = run_mass(rig)

    sent = b"".join(authz_puts(rig))
    assert result.findings == ()
    assert b"nivelAcesso" not in sent
    assert b"saldo" not in sent


def test_the_limit_of_derived_candidates_cuts_and_says_how_many() -> None:
    rig = derived_rig(Clinic(stores=("nivelAcesso", "saldo")), max_derived_candidates=1)

    result = run_mass(rig)

    sent = b"".join(authz_puts(rig))
    assert b"nivelAcesso" in sent
    assert b"saldo" not in sent
    cut = notes(result, "candidates_limited")
    assert len(cut) == 1
    assert "1 campo" in cut[0].message


def test_a_derived_field_already_at_the_test_value_is_skipped_not_guessed() -> None:
    rig = derived_rig(Clinic(stores=("nivelAcesso",)))
    rig.clinic.extra["pac_a"]["nivelAcesso"] = "admin"

    result = run_mass(rig)

    assert notes(result, "already_in_target_state")
    assert all(b"nivelAcesso" not in body for body in authz_puts(rig))


def test_nothing_is_sent_without_allow_writes_even_with_derived_candidates() -> None:
    rig = derived_rig(Clinic(stores=("nivelAcesso", "saldo")), allow_writes=False)

    result = run_mass(rig)

    assert result.findings == ()
    assert authz_puts(rig) == []
    assert len(notes(result, "writes_not_authorized")) == 1


def test_a_stop_after_the_put_of_a_derived_field_still_reports_the_unrestored_change() -> None:
    rig = derived_rig(Clinic(stores=("nivelAcesso",)))

    class ClosesAfterPut:
        def engaged(self) -> bool:
            return any(
                r.method == "PUT" and r.operation_id.startswith("authz:")
                for r in rig.target.requests
            )

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
        kill_switch=ClosesAfterPut(),
    )
    result = stage.execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )

    assert result.status == "stopped_window"
    assert any(n.reason == "possible_unrestored_change" for n in result.not_tested)


def test_the_run_ceiling_stops_new_writes_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authz_checks_mass, "MAX_MASS_REQUESTS", 2)
    rig = derived_rig(Clinic(stores=("nivelAcesso", "saldo")))

    result = run_mass(rig)

    # Reserva uma escrita para eventual restauração da última alteração.
    assert len(authz_puts(rig)) == 1
    assert notes(result, "budget_exhausted")


def test_delete_is_never_sent() -> None:
    rig = derived_rig(Clinic(stores=("nivelAcesso",)))

    run_mass(rig)

    assert all(r.method != "DELETE" for r in rig.target.requests)


def test_the_finding_is_in_the_result_with_its_source_and_never_with_values() -> None:
    rig = derived_rig(Clinic(stores=("nivelAcesso",)))

    result = run_mass(rig)

    dumped = result.model_dump_json()
    assert '"candidate_source":"response_only"' in dumped
    assert '"admin"' not in dumped


def test_the_dry_run_lists_the_candidates_with_their_source_and_sends_nothing() -> None:
    rig = derived_rig(Clinic(stores=("nivelAcesso", "saldo")))
    probe = rig.run_probe()
    before = len(rig.target.requests)

    result = rig.authz().execute(
        AuthzRequest(
            product="agenda", run_id=probe.run_id, checks=("mass_assignment",), dry_run=True
        )
    )

    summary = next(c for c in result.checks if c.check == "mass_assignment")
    assert summary.candidates == 6
    assert summary.message is not None
    assert "nivelAcesso (response_only)" in summary.message
    assert "saldo (response_only)" in summary.message
    assert len(rig.target.requests) == before
    assert result.requests_sent == 0


def test_reader_proven_by_other_account_confirms_and_restores_writer() -> None:
    rig = derived_rig(Clinic(stores=("saldo",)))
    probe = rig.run_probe()
    log = rig.store.exchanges[probe.run_id]
    rig.store.exchanges[probe.run_id] = log.model_copy(
        update={
            "exchanges": tuple(
                item.model_copy(update={"account": "pac_b"})
                if item.method == "GET" and item.path == "/api/me"
                else item
                for item in log.exchanges
            )
        }
    )

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("mass_assignment",))
    )

    assert any(f.fields == ("saldo",) for f in result.findings)
    assert rig.clinic.extra["pac_a"]["saldo"] == 10
    reads = [
        r
        for r in rig.target.requests
        if r.method == "GET" and r.operation_id.startswith("authz:") and r.url.endswith("/api/me")
    ]
    assert reads
    assert all(r.account == "pac_a" for r in reads)
