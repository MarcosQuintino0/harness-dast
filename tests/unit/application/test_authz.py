"""`authz`: o estágio acha cada falha quando ela existe e não acusa quando não existe."""

from typing import Any

import pytest

from harness_dast.application.authz import AuthzRequest
from harness_dast.domain.authz_result import AuthzFinding, AuthzResult
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_exchange import ExchangeLog, ExchangeRecord
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.profile import ProductProfile
from tests.fakes.authz_rig import (
    ENV,
    HASH_VALUE,
    NOTES_VALUE,
    AuthzRig,
    Clinic,
    clinic_profile_data,
    token_of,
)


def probed(rig: AuthzRig) -> ProbeResult:
    return rig.run_probe()


def run_authz(rig: AuthzRig, **changes: Any) -> AuthzResult:
    probe = probed(rig)
    return rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id, **changes))


def by_technique(result: AuthzResult, technique: str) -> list[AuthzFinding]:
    return [item for item in result.findings if item.technique == technique]


def check(result: AuthzResult, name: str) -> Any:
    return next(item for item in result.checks if item.check == name)


# --- 1. acesso horizontal (BOLA) ------------------------------------------------------


def test_finds_bola_when_another_account_of_the_same_role_reads_the_resource() -> None:
    rig = AuthzRig(Clinic(bola=True))

    result = run_authz(rig, checks=("horizontal",))

    found = by_technique(result, "authz_horizontal")
    assert [(f.operation_id, f.actor_account, f.owner_account) for f in found] == [
        ("buscarConsulta", "pac_b", "pac_a")
    ]
    assert found[0].proposed_severity == "high"
    assert found[0].origin == "authz"
    assert found[0].method == "GET"
    assert found[0].path_template == "/api/consultas/{}"


def test_does_not_accuse_when_the_other_account_is_denied() -> None:
    rig = AuthzRig(Clinic(bola=False))

    result = run_authz(rig, checks=("horizontal",))

    assert by_technique(result, "authz_horizontal") == []
    summary = check(result, "horizontal")
    assert summary.status == "completed"
    assert summary.tested >= 1


def test_a_public_operation_declared_in_the_profile_is_not_an_alarm() -> None:
    open_catalogue = AuthzRig(Clinic(), authz={"public_operations": []})
    declared = AuthzRig(Clinic())

    without = run_authz(open_catalogue, checks=("horizontal",))
    with_declaration = run_authz(declared, checks=("horizontal",))

    assert [f.operation_id for f in without.findings] == ["lerCatalogo"]
    assert with_declaration.findings == ()
    assert any(
        n.operation_id == "lerCatalogo" and n.reason == "public_operation"
        for n in with_declaration.not_tested
    )


def test_ignores_volatile_fields_when_comparing_responses() -> None:
    rig = AuthzRig(Clinic(bola=True))

    run_authz(rig, checks=("horizontal",))

    # o `requestId` da fake muda a cada resposta: só a comparação sem campos voláteis acha
    bodies = [r for r in rig.target.requests if "/api/consultas/" in r.url]
    assert len(bodies) >= 2


def test_reports_what_could_not_be_tested_when_there_is_no_second_account_of_the_role() -> None:
    data = clinic_profile_data()
    data["auth"]["accounts"] = [a for a in data["auth"]["accounts"] if a["alias"] != "pac_b"]
    rig = AuthzRig(Clinic(bola=True), profile=ProductProfile.from_data(data))

    result = run_authz(rig, checks=("horizontal",))

    assert result.findings == ()
    assert check(result, "horizontal").status == "skipped"
    reasons = {n.reason for n in result.not_tested if n.check == "horizontal"}
    assert "no_peer_account" in reasons


def test_collections_without_an_identifier_are_not_compared_between_accounts() -> None:
    result = run_authz(AuthzRig(Clinic(bola=True)), checks=("horizontal",))

    reasons = {(n.operation_id, n.reason) for n in result.not_tested}
    assert ("listarPacientes", "no_path_parameter") in reasons


def test_a_failing_baseline_is_not_tested_instead_of_green() -> None:
    clinic = Clinic(bola=False)
    rig = AuthzRig(clinic)
    probe = probed(rig)
    rig.clinic.bola = False
    # troca o dono: depois do probe, pac_a deixa de ler (linha de base falha)
    original = clinic._route

    def deny_owner(request: Any, path: str, alias: str) -> Any:
        if path.startswith("api/consultas/"):
            from tests.fakes.probe_ports import reply

            return reply(403, {"code": "ACESSO_NEGADO"})
        return original(request, path, alias)

    clinic._route = deny_owner  # type: ignore[method-assign]  # troca o comportamento do falso

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("horizontal",))
    )

    assert result.findings == ()
    assert any(n.reason == "baseline_failed" for n in result.not_tested)


# --- 2. dado a mais -------------------------------------------------------------------


def test_finds_fields_outside_the_schema_and_raises_severity_for_secret_names() -> None:
    rig = AuthzRig(Clinic(excess=True))

    result = run_authz(rig, checks=("excessive_data",))

    found = by_technique(result, "authz_excessive_data")
    assert len(found) == 1
    assert found[0].operation_id == "listarPacientes"
    assert set(found[0].fields) == {"items[].passwordHash", "items[].internalNotes"}
    assert found[0].proposed_severity == "high"


def test_does_not_accuse_when_the_response_matches_the_schema() -> None:
    result = run_authz(AuthzRig(Clinic(excess=False)), checks=("excessive_data",))

    assert result.findings == ()
    assert check(result, "excessive_data").tested >= 1


def test_an_empty_list_is_not_tested_instead_of_counted_as_safe() -> None:
    rig = AuthzRig(Clinic(excess=True, empty_lists=True))

    result = run_authz(rig, checks=("excessive_data",))

    reasons = [n.reason for n in result.not_tested if n.operation_id == "listarPacientes"]
    assert reasons == ["no_sample_data"]
    assert result.findings == ()
    summary = check(result, "excessive_data")
    assert summary.tested < summary.candidates


def test_never_writes_the_value_of_the_suspect_field() -> None:
    rig = AuthzRig(Clinic(excess=True))

    run_authz(rig)

    everything = rig.store.serialized() + rig.artifacts.serialized()
    assert HASH_VALUE not in everything
    assert NOTES_VALUE not in everything


# --- 3. acesso vertical (BFLA) ---------------------------------------------------------


def test_finds_vertical_access_when_a_lower_role_succeeds() -> None:
    rig = AuthzRig(Clinic(bfla=True))

    result = run_authz(rig, checks=("vertical",))

    found = by_technique(result, "authz_vertical")
    assert [(f.operation_id, f.actor_account, f.actor_role, f.owner_role) for f in found] == [
        ("listarRelatorios", "pac_a", "paciente", "admin")
    ]
    assert found[0].proposed_severity == "high"


def test_does_not_accuse_when_the_lower_role_gets_403() -> None:
    result = run_authz(AuthzRig(Clinic(bfla=False)), checks=("vertical",))

    assert result.findings == ()
    assert check(result, "vertical").tested == 1


def test_writes_are_only_repeated_when_the_profile_lists_the_method() -> None:
    defaults = AuthzRig(Clinic(bfla=True))
    opted_in = AuthzRig(Clinic(bfla=True), authz={"vertical_methods": ["GET", "POST"]})

    run_authz(defaults, checks=("vertical",))
    result = run_authz(opted_in, checks=("vertical",))

    assert not [
        r for r in defaults.sent_by("pac_a") if r.method == "POST" and "authz" in r.operation_id
    ]
    assert {f.operation_id for f in result.findings} == {"listarRelatorios", "criarConvenio"}


def test_vertical_needs_the_role_order_and_says_so() -> None:
    data = clinic_profile_data()
    del data["authz"]["role_order"]
    rig = AuthzRig(Clinic(bfla=True), profile=ProductProfile.from_data(data))

    result = run_authz(rig, checks=("vertical",))

    assert result.findings == ()
    assert [n.reason for n in result.not_tested] == ["no_role_order"]


def test_operations_served_only_by_the_default_account_are_not_repeated_vertically() -> None:
    rig = AuthzRig(Clinic(bfla=True))

    result = run_authz(rig, checks=("vertical",))

    assert "listarPacientes" not in {f.operation_id for f in result.findings}
    assert not [r for r in rig.sent_by("pac_a") if r.url.endswith("/api/pacientes")]


# --- 4. campo a mais (atribuição em massa) -----------------------------------------------


def test_finds_mass_assignment_even_when_the_changed_field_has_another_name() -> None:
    rig = AuthzRig(Clinic(mass=True))

    result = run_authz(rig, checks=("mass_assignment",))

    found = by_technique(result, "authz_mass_assignment")
    assert [f.operation_id for f in found] == ["atualizarPerfil"]
    assert found[0].fields == ("role", "papel")
    assert found[0].proposed_severity == "high"
    assert found[0].actor_account == "pac_a"


def test_restores_the_previous_value_after_a_mass_assignment_finding() -> None:
    rig = AuthzRig(Clinic(mass=True))

    result = run_authz(rig, checks=("mass_assignment",))

    assert rig.clinic.papel["pac_a"] == "paciente"
    assert "restaurado" in result.findings[0].evidence


def test_does_not_accuse_when_the_extra_field_is_ignored() -> None:
    rig = AuthzRig(Clinic(mass=False))

    result = run_authz(rig, checks=("mass_assignment",))

    assert result.findings == ()
    assert check(result, "mass_assignment").tested == 4


def test_a_target_that_rejects_unknown_fields_is_a_tested_negative() -> None:
    rig = AuthzRig(Clinic(mass=False, reject_extra_fields=True))

    result = run_authz(rig, checks=("mass_assignment",))

    assert result.findings == ()
    assert check(result, "mass_assignment").tested == 4


def test_a_field_the_probe_already_sent_with_the_test_value_is_not_tested() -> None:
    rig = AuthzRig(
        Clinic(mass=True),
        authz={"mass_assignment_fields": [{"name": "role", "value": "paciente"}]},
    )

    result = run_authz(rig, checks=("mass_assignment",))

    assert result.findings == ()
    assert [n.reason for n in result.not_tested] == ["same_value_in_body"]
    assert check(result, "mass_assignment").status == "skipped"


def test_a_declared_field_that_the_probe_sent_with_another_value_is_overridden() -> None:
    rig = AuthzRig(Clinic(mass=True))

    result = run_authz(rig, checks=("mass_assignment",))

    puts = [r for r in rig.target.requests if r.method == "PUT" and "authz" in r.operation_id]
    assert any(b'"role":"admin"' in (r.body or b"") for r in puts)
    assert [f.fields for f in result.findings] == [("role", "papel")]


def test_only_the_declared_extra_fields_are_sent() -> None:
    rig = AuthzRig(
        Clinic(mass=True),
        authz={"mass_assignment_fields": [{"name": "role", "value": "admin"}]},
    )

    run_authz(rig, checks=("mass_assignment",))

    puts = [
        r for r in rig.target.requests if r.method == "PUT" and r.operation_id.startswith("authz:")
    ]
    assert puts
    assert all(b"papel" not in (r.body or b"") for r in puts)
    assert all(b"isAdmin" not in (r.body or b"") for r in puts)


# --- alvo vulnerável contra alvo seguro ------------------------------------------------------


def test_a_vulnerable_target_yields_one_finding_per_technique() -> None:
    rig = AuthzRig(Clinic(bola=True, excess=True, mass=True, bfla=True))

    result = run_authz(rig)

    assert {f.technique for f in result.findings} == {
        "authz_horizontal",
        "authz_excessive_data",
        "authz_vertical",
        "authz_mass_assignment",
    }
    assert {f.proposed_severity for f in result.findings} == {"high"}
    assert result.status == "completed"
    assert result.accounts


def test_a_safe_target_yields_no_finding_and_still_says_what_it_did_not_test() -> None:
    rig = AuthzRig(Clinic())

    result = run_authz(rig)

    assert result.findings == ()
    assert result.status == "completed"
    assert [c.status for c in result.checks] == ["completed"] * 4
    assert result.not_tested
    assert "NÃO prova" in result.notice


# --- regras inegociáveis ---------------------------------------------------------------


def test_every_request_goes_through_the_same_guarded_path_with_audit() -> None:
    rig = AuthzRig(Clinic(bola=True, excess=True, mass=True, bfla=True))
    probe = probed(rig)
    before = len(rig.store.audit[probe.run_id])

    rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id))

    entries = rig.store.audit[probe.run_id][before:]
    sent = [e for e in entries if e.phase == "decision" and e.decision == "allowed"]
    assert sent
    assert all(e.operation_id.startswith(("authz:", "auth.")) for e in entries)
    seqs = [e.seq for e in rig.store.audit[probe.run_id] if e.phase == "decision"]
    assert len(seqs) == len(set(seqs))


def test_never_repeats_delete_even_if_the_log_has_one() -> None:
    rig = AuthzRig(Clinic(bola=True))
    probe = probed(rig)
    log = rig.store.exchanges[probe.run_id]
    delete = ExchangeRecord(
        operation_id="remover",
        method="DELETE",
        path="/api/consultas/{id}",
        target="/api/consultas/9",
        account="pac_a",
        status=200,
    )
    rig.store.exchanges[probe.run_id] = log.model_copy(
        update={"exchanges": (*log.exchanges, delete)}
    )

    rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id))

    assert not [r for r in rig.target.requests if r.method == "DELETE"]


def test_a_target_outside_the_scope_is_refused_and_nothing_is_sent() -> None:
    rig = AuthzRig(Clinic(bola=True))
    probe = probed(rig)
    outside = ExchangeRecord(
        operation_id="buscarConsulta",
        method="GET",
        path="/api/consultas/{id}",
        target="/api/admin/consultas/1",
        account="pac_a",
        status=200,
    )
    rig.store.exchanges[probe.run_id] = ExchangeLog(
        run_id=probe.run_id, product="agenda", exchanges=(outside,)
    )

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=("horizontal",))
    )

    assert not [r for r in rig.target.requests if "/api/admin/" in r.url]
    assert {n.reason for n in result.not_tested} == {"scope_denied"}


def test_never_writes_secrets_tokens_or_passwords() -> None:
    rig = AuthzRig(Clinic(bola=True, excess=True, mass=True, bfla=True))

    run_authz(rig)

    everything = rig.store.serialized() + rig.artifacts.serialized()
    secrets = [*ENV.values(), *(token_of(a) for a in ("pac_a", "pac_b", "adm"))]
    assert not [s for s in secrets if s in everything]


def test_an_account_that_cannot_log_in_is_reported_not_tested() -> None:
    rig = AuthzRig(Clinic(bola=True))
    rig.secrets._values["ACME_USER_B_LOGIN"] = "desconhecido"

    result = run_authz(rig, checks=("horizontal",))

    assert result.findings == ()
    assert any(n.reason == "account_unavailable" for n in result.not_tested)


def test_dry_run_plans_without_sending_or_writing() -> None:
    rig = AuthzRig(Clinic(bola=True))
    probe = probed(rig)
    sent_before = len(rig.target.requests)

    result = rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id, dry_run=True))

    assert len(rig.target.requests) == sent_before
    assert result.dry_run
    assert result.requests_sent == 0
    assert rig.artifacts.authz == {}
    assert check(result, "horizontal").candidates == 1


def test_the_result_is_written_and_lists_every_check_in_a_fixed_order() -> None:
    rig = AuthzRig(Clinic())

    result = run_authz(rig, checks=("horizontal",))

    assert rig.artifacts.authz[result.run_id] == result
    assert [c.check for c in result.checks] == [
        "horizontal",
        "excessive_data",
        "vertical",
        "mass_assignment",
    ]
    assert [c.status for c in result.checks][1:] == ["disabled"] * 3


def test_checks_disabled_in_the_profile_never_run_even_when_asked() -> None:
    rig = AuthzRig(Clinic(mass=True), authz={"disabled_checks": ["mass_assignment"]})

    result = run_authz(rig, checks=("mass_assignment",))

    assert check(result, "mass_assignment").status == "disabled"
    assert not [r for r in rig.target.requests if r.method == "PUT" and "authz" in r.operation_id]


def test_a_kill_switch_engaged_stops_the_stage_with_a_partial_result() -> None:
    from harness_dast.application.authz import Authz

    class Engaged:
        def engaged(self) -> bool:
            return True

    rig = AuthzRig(Clinic(bola=True))
    probe = probed(rig)
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
        kill_switch=Engaged(),
    )

    result = stage.execute(AuthzRequest(product="agenda", run_id=probe.run_id))

    assert result.status == "stopped_window"
    assert result.findings == ()
    assert result.stop_message


# --- entradas inválidas, ausentes e malformadas -----------------------------------------


def test_an_unknown_run_is_a_config_error() -> None:
    rig = AuthzRig()

    with pytest.raises(ConfigError):
        rig.authz().execute(
            AuthzRequest(product="agenda", run_id="2026-11-13T00-00-00Z-agenda-abcd")
        )


def test_a_malformed_run_id_is_a_config_error() -> None:
    rig = AuthzRig()

    with pytest.raises(ConfigError):
        rig.authz().execute(AuthzRequest(product="agenda", run_id="../etc"))


def test_a_run_without_exchanges_is_a_config_error() -> None:
    rig = AuthzRig()
    probe = probed(rig)
    del rig.store.exchanges[probe.run_id]

    with pytest.raises(ConfigError, match="exchanges"):
        rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id))


def test_a_probe_dry_run_cannot_feed_the_stage() -> None:
    from harness_dast.application.probe import ProbeRequest

    rig = AuthzRig()
    dry = rig.probe().execute(ProbeRequest(product="agenda", dry_run=True))
    rig.store.probes[dry.run_id] = dry
    rig.store.exchanges[dry.run_id] = ExchangeLog(run_id=dry.run_id, product="agenda")

    with pytest.raises(ConfigError, match="simulação"):
        rig.authz().execute(AuthzRequest(product="agenda", run_id=dry.run_id))


def test_a_run_of_another_product_is_refused() -> None:
    rig = AuthzRig()
    probe = probed(rig)
    rig.store.exchanges[probe.run_id] = ExchangeLog(run_id=probe.run_id, product="outro")

    with pytest.raises(ConfigError, match="outro produto"):
        rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id))


def test_a_public_operation_that_does_not_exist_is_a_config_error() -> None:
    rig = AuthzRig(authz={"public_operations": ["inexistente"]})
    probe = probed(rig)

    with pytest.raises(ConfigError, match="inexistente"):
        rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id))


def test_the_probe_records_only_successful_requests_without_secrets() -> None:
    rig = AuthzRig(Clinic())

    probe = probed(rig)

    log = rig.store.exchanges[probe.run_id]
    assert {e.operation_id for e in log.exchanges} >= {"buscarConsulta", "atualizarPerfil"}
    assert all(e.status < 300 for e in log.exchanges)
    assert "auth.login" not in {e.operation_id for e in log.exchanges}
    assert not any(secret in log.model_dump_json() for secret in ENV.values())
