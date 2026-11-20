"""`authz`: pedido sem login e token adulterado (ADR 0039)."""

from datetime import timedelta
from typing import Any

import pytest

from harness_dast.application.authz import checks_access
from harness_dast.application.authz.service import Authz, AuthzRequest
from harness_dast.domain.api_model import ApiSpec, SecurityRequirement
from harness_dast.domain.authz.config import AuthzCheck
from harness_dast.domain.authz.result import AuthzFinding, AuthzNotTested, AuthzResult
from harness_dast.domain.authz.token import build_tampered_tokens
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.probe_exchange import ExchangeLog, ExchangeRecord
from tests.fakes.authz.rig import ROLES, AuthzRig, Clinic, clinic_spec

OPEN = frozenset({"api/pacientes"})
ANON: AuthzCheck = "anonymous_access"
TAMPER: AuthzCheck = "tampered_token"


def run_authz(rig: AuthzRig, **changes: Any) -> AuthzResult:
    probe = rig.run_probe()
    return rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id, **changes))


def found(result: AuthzResult, technique: str) -> list[AuthzFinding]:
    return [item for item in result.findings if item.technique == technique]


def summary(result: AuthzResult, name: str) -> Any:
    return next(item for item in result.checks if item.check == name)


def notes(result: AuthzResult, check: str, reason: str) -> list[AuthzNotTested]:
    return [n for n in result.not_tested if n.check == check and n.reason == reason]


def sent(rig: AuthzRig, prefix: str) -> list[HttpRequest]:
    return [r for r in rig.target.requests if r.operation_id.startswith(prefix)]


def header(request: HttpRequest, name: str) -> str | None:
    return dict(request.headers).get(name)


def spec_without_security(operation_id: str) -> ApiSpec:
    spec = clinic_spec()
    changed = tuple(
        op.model_copy(update={"security": ()}) if op.operation_id == operation_id else op
        for op in spec.operations
    )
    return spec.model_copy(update={"operations": changed})


# --- pedido sem login -------------------------------------------------------------------------


def test_anonymous_request_reaches_the_target_without_credential_cookie_or_account() -> None:
    rig = AuthzRig(Clinic(open_paths=OPEN))

    run_authz(rig, checks=(ANON,))

    requests = sent(rig, "authz:anonymous:")
    assert requests
    for request in requests:
        assert request.account is None
        assert header(request, "Authorization") is None
        assert header(request, "Cookie") is None
        assert request.method == "GET"


def test_anonymous_access_is_a_high_finding_when_the_openapi_requires_authentication() -> None:
    rig = AuthzRig(Clinic(open_paths=OPEN))

    result = run_authz(rig, checks=(ANON,))

    [finding] = found(result, "authz_anonymous_access")
    assert finding.operation_id == "listarPacientes"
    assert finding.proposed_severity == "high"
    assert finding.cwe == 306
    assert finding.actor_account == "adm"
    assert (finding.baseline_status, finding.observed_status) == (200, 200)
    assert summary(result, ANON).findings == 1


def test_anonymous_access_is_medium_when_the_openapi_declares_no_security() -> None:
    rig = AuthzRig(Clinic(open_paths=OPEN), spec=spec_without_security("listarPacientes"))

    result = run_authz(rig, checks=(ANON,))

    [finding] = found(result, "authz_anonymous_access")
    assert finding.proposed_severity == "medium"


def test_a_protected_target_yields_no_anonymous_finding_and_counts_the_tests() -> None:
    rig = AuthzRig(Clinic())

    result = run_authz(rig, checks=(ANON,))

    assert result.findings == ()
    assert summary(result, ANON).status == "completed"
    assert summary(result, ANON).tested >= 1


def test_a_different_body_for_anonymous_counts_as_tested_without_finding() -> None:
    rig = AuthzRig(Clinic(open_paths=OPEN, open_different=True))

    result = run_authz(rig, checks=(ANON,))

    assert found(result, "authz_anonymous_access") == []
    assert summary(result, ANON).tested >= 1


def test_a_server_error_without_credential_is_inconclusive_never_safe() -> None:
    rig = AuthzRig(Clinic(unauth_status=500))

    result = run_authz(rig, checks=(ANON,))

    assert result.findings == ()
    assert notes(result, ANON, "inconclusive")
    assert summary(result, ANON).status == "skipped"


def test_public_declared_and_infrastructure_operations_are_not_tested_with_a_reason() -> None:
    rig = AuthzRig(Clinic(open_paths=OPEN | {"api/catalogo/1"}))

    result = run_authz(rig, checks=(ANON,))

    assert [n.operation_id for n in notes(result, ANON, "public_operation")] == ["lerCatalogo"]
    assert all(r.operation_id != "authz:anonymous:lerCatalogo" for r in rig.target.requests)
    public = notes(result, ANON, "public_operation")[0]
    assert "public_operations" in public.message


def test_an_operation_the_openapi_declares_anonymous_is_skipped_with_a_reason() -> None:
    spec = clinic_spec()
    changed = tuple(
        op.model_copy(update={"security": (SecurityRequirement(),)})
        if op.operation_id == "listarPacientes"
        else op
        for op in spec.operations
    )
    rig = AuthzRig(Clinic(open_paths=OPEN), spec=spec.model_copy(update={"operations": changed}))

    result = run_authz(rig, checks=(ANON,))

    assert [n.operation_id for n in notes(result, ANON, "declared_public")] == ["listarPacientes"]
    assert found(result, "authz_anonymous_access") == []


def test_the_health_path_is_infrastructure_and_never_repeated_without_login() -> None:
    rig = AuthzRig(Clinic())
    probe = rig.run_probe()
    health = ExchangeRecord(
        operation_id="saude",
        method="GET",
        path="/api/saude",
        target="/api/saude",
        account="adm",
        status=200,
    )
    rig.store.exchanges[probe.run_id] = ExchangeLog(
        run_id=probe.run_id, product="agenda", exchanges=(health,)
    )

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=(ANON,))
    )

    assert [n.reason for n in notes(result, ANON, "infrastructure_path")] == ["infrastructure_path"]
    assert sent(rig, "authz:anonymous:") == []


def test_an_out_of_scope_target_is_refused_for_both_checks_and_nothing_is_sent() -> None:
    rig = AuthzRig(Clinic(open_paths=OPEN))
    probe = rig.run_probe()
    outside = ExchangeRecord(
        operation_id="listarPacientes",
        method="GET",
        path="/api/pacientes",
        target="/api/admin/pacientes",
        account="adm",
        status=200,
    )
    rig.store.exchanges[probe.run_id] = ExchangeLog(
        run_id=probe.run_id, product="agenda", exchanges=(outside,)
    )

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=(ANON, TAMPER))
    )

    assert not [r for r in rig.target.requests if "/api/admin/" in r.url]
    assert {(n.check, n.reason) for n in result.not_tested} == {
        (ANON, "scope_denied"),
        (TAMPER, "scope_denied"),
    }


def test_every_access_request_goes_through_the_audit_trail_without_an_account() -> None:
    rig = AuthzRig(Clinic(lax="any_token"))

    result = run_authz(rig, checks=(ANON, TAMPER))

    audit = rig.store.audit[result.run_id]
    access = [
        e for e in audit if (e.operation_id or "").startswith(("authz:anonymous", "authz:tampered"))
    ]
    assert access
    assert {e.account for e in access} == {None}
    assert {e.decision for e in access if e.phase == "decision"} == {"allowed"}
    sequence = [e.seq for e in audit]
    assert sequence == sorted(sequence)


def test_a_window_closed_stops_the_access_checks_like_any_other() -> None:
    class Engaged:
        def engaged(self) -> bool:
            return True

    rig = AuthzRig(Clinic(open_paths=OPEN))
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
        kill_switch=Engaged(),
    )

    result = stage.execute(AuthzRequest(product="agenda", run_id=probe.run_id, checks=(ANON,)))

    assert result.status == "stopped_window"
    assert result.findings == ()


def test_an_exhausted_deadline_stops_the_access_checks_before_any_request() -> None:
    rig = AuthzRig(Clinic(open_paths=OPEN))
    probe = rig.run_probe()
    before = len(rig.target.requests)

    result = rig.authz().execute(
        AuthzRequest(
            product="agenda",
            run_id=probe.run_id,
            checks=(ANON, TAMPER),
            deadline=rig.clock.now() - timedelta(seconds=1),
        )
    )

    assert result.status == "stopped_deadline"
    assert len(rig.target.requests) == before


# --- token adulterado -------------------------------------------------------------------------


def test_a_strict_server_refuses_the_tampered_opaque_token_and_no_finding_is_raised() -> None:
    rig = AuthzRig(Clinic())

    result = run_authz(rig, checks=(TAMPER,))

    assert result.findings == ()
    assert summary(result, TAMPER).tested >= 1
    assert summary(result, TAMPER).status == "completed"


def test_tampered_requests_carry_the_scrambled_token_never_the_original_and_no_cookie() -> None:
    rig = AuthzRig(Clinic())

    run_authz(rig, checks=(TAMPER,))

    requests = sent(rig, "authz:tampered:")
    assert requests
    originals = {f"Bearer {rig.clinic.issue(alias)}" for alias in ROLES}
    for request in requests:
        value = header(request, "Authorization")
        assert value is not None
        assert value not in originals
        assert value.startswith("Bearer ")
        assert request.account is None
        assert header(request, "Cookie") is None


def test_an_opaque_token_costs_one_request_per_operation_and_a_401_never_resends() -> None:
    rig = AuthzRig(Clinic())
    probe = rig.run_probe()
    logins = rig.clinic.logins

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=(TAMPER,))
    )

    tampered = sent(rig, "authz:tampered:")
    operations = [r.operation_id for r in tampered]
    assert len(operations) == len(set(operations)) == summary(result, TAMPER).tested
    assert rig.clinic.logins - logins == len(result.accounts)


def test_a_server_that_accepts_any_token_gets_a_high_finding_with_cwe_287() -> None:
    rig = AuthzRig(Clinic(lax="any_token"))

    result = run_authz(rig, checks=(TAMPER,))

    findings = found(result, "authz_tampered_token")
    assert {f.operation_id for f in findings} == {
        "obterPerfil",
        "buscarConsulta",
        "listarPacientes",
        "listarRelatorios",
    }
    for finding in findings:
        assert finding.proposed_severity == "high"
        assert finding.cwe == 287
        assert finding.variants == ("scrambled",)
        assert finding.owner_account is None
        assert finding.fields == ()


def test_a_jwt_server_that_ignores_the_signature_accepts_all_three_variants_cwe_347() -> None:
    rig = AuthzRig(Clinic(jwt=True, lax="ignore_signature"))

    result = run_authz(rig, checks=(TAMPER,))

    findings = found(result, "authz_tampered_token")
    assert findings
    for finding in findings:
        assert finding.variants == ("stripped_signature", "alg_none", "altered_claims")
        assert finding.cwe == 347
    assert len(sent(rig, "authz:tampered:")) == 3 * len(findings)


def test_a_strict_jwt_server_refuses_every_variant() -> None:
    rig = AuthzRig(Clinic(jwt=True))

    result = run_authz(rig, checks=(TAMPER,))

    assert result.findings == ()
    assert summary(result, TAMPER).tested >= 1


def test_the_tampered_check_skips_an_operation_that_already_answers_without_login() -> None:
    rig = AuthzRig(Clinic(lax="any_token", open_paths=OPEN))

    result = run_authz(rig, checks=(TAMPER,))

    assert [n.operation_id for n in notes(result, TAMPER, "anonymous_already_open")] == [
        "listarPacientes"
    ]
    assert all(r.operation_id != "authz:tampered:listarPacientes" for r in rig.target.requests)
    assert "listarPacientes" not in {f.operation_id for f in result.findings}


def test_the_tampered_check_alone_sends_the_anonymous_request_once_per_operation() -> None:
    rig = AuthzRig(Clinic())

    run_authz(rig, checks=(TAMPER,))

    operations = [r.operation_id for r in sent(rig, "authz:anonymous:")]
    assert operations
    assert len(operations) == len(set(operations))


def test_running_both_checks_reuses_the_anonymous_answer() -> None:
    rig = AuthzRig(Clinic())

    run_authz(rig, checks=(ANON, TAMPER))

    operations = [r.operation_id for r in sent(rig, "authz:anonymous:")]
    assert len(operations) == len(set(operations))


def test_a_server_error_in_a_variant_is_inconclusive_never_safe() -> None:
    rig = AuthzRig(Clinic())
    probe = rig.run_probe()
    original = rig.target._handler

    def flaky(request: Any, jar: Any) -> Any:
        if request.operation_id == "authz:tampered:listarRelatorios":
            from tests.fakes.probe_ports import reply

            return reply(500, {})
        return original(request, jar)

    rig.target._handler = flaky

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=(TAMPER,))
    )

    assert "listarRelatorios" in {n.operation_id for n in notes(result, TAMPER, "inconclusive")}
    assert result.findings == ()


def test_a_token_that_cannot_be_scrambled_is_not_tested_with_a_reason() -> None:
    rig = AuthzRig(Clinic())
    probe = rig.run_probe()
    rig.clinic.issue = lambda alias: "x"  # type: ignore[method-assign]

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=(TAMPER,))
    )

    assert "obterPerfil" in {n.operation_id for n in notes(result, TAMPER, "token_too_short")}
    assert sent(rig, "authz:tampered:") == []


def test_dry_run_lists_candidates_and_not_tested_for_the_new_checks_without_sending() -> None:
    rig = AuthzRig(Clinic(open_paths=OPEN))
    probe = rig.run_probe()
    before = len(rig.target.requests)

    result = rig.authz().execute(AuthzRequest(product="agenda", run_id=probe.run_id, dry_run=True))

    assert len(rig.target.requests) == before
    assert summary(result, ANON).candidates >= 1
    assert summary(result, TAMPER).candidates >= 1
    assert notes(result, ANON, "public_operation")
    assert notes(result, TAMPER, "public_operation")


def test_disabling_the_new_checks_in_the_profile_keeps_them_off() -> None:
    rig = AuthzRig(Clinic(open_paths=OPEN), authz={"disabled_checks": [ANON, TAMPER]})

    result = run_authz(rig)

    assert summary(result, ANON).status == "disabled"
    assert summary(result, TAMPER).status == "disabled"
    assert sent(rig, "authz:anonymous:") == []
    assert sent(rig, "authz:tampered:") == []


def test_exchanges_without_any_get_say_no_read_exchange() -> None:
    rig = AuthzRig(Clinic())
    probe = rig.run_probe()
    post = ExchangeRecord(
        operation_id="criarConvenio",
        method="POST",
        path="/api/convenios",
        target="/api/convenios",
        account="adm",
        status=201,
        content_type="application/json",
        body='{"nome":"x"}',
    )
    rig.store.exchanges[probe.run_id] = ExchangeLog(
        run_id=probe.run_id, product="agenda", exchanges=(post,)
    )

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=probe.run_id, checks=(ANON, TAMPER))
    )

    assert notes(result, ANON, "no_read_exchange")
    assert notes(result, TAMPER, "no_read_exchange")


# --- o valor do token nunca vaza --------------------------------------------------------------


def test_no_token_original_or_tampered_reaches_any_artifact_message_or_audit() -> None:
    for clinic in (Clinic(lax="any_token"), Clinic(jwt=True, lax="ignore_signature")):
        rig = AuthzRig(clinic)

        result = run_authz(rig, checks=(ANON, TAMPER))

        secrets: set[str] = set()
        for alias in ROLES:
            token = clinic.issue(alias)
            secrets.add(token)
            secrets.update(
                item.value for item in build_tampered_tokens(token, allow_jwt=clinic.jwt)
            )
        stored = rig.artifacts.authz[result.run_id]
        text = (
            result.model_dump_json()
            + stored.model_dump_json()
            + "".join(e.model_dump_json() for e in rig.store.audit[result.run_id])
            + "".join(n.message for n in result.not_tested)
        )
        assert secrets
        for secret in secrets:
            assert secret not in text


def test_every_tampered_value_is_registered_for_masking_before_it_is_sent() -> None:
    rig = AuthzRig(Clinic())

    run_authz(rig, checks=(TAMPER,))

    for request in sent(rig, "authz:tampered:"):
        value = header(request, "Authorization") or ""
        assert value.removeprefix("Bearer ") not in rig.vault.mask(value)


# --- chave HMAC fraca (ADR 0098) ----------------------------------------------------------------

STRONG_KEY = "k9#Qz-8vLm2$Xr7@pW4^tB6&"


def tampered_by_operation(rig: AuthzRig) -> dict[str, int]:
    counts: dict[str, int] = {}
    for request in sent(rig, "authz:tampered:"):
        counts[request.operation_id] = counts.get(request.operation_id, 0) + 1
    return counts


def test_a_server_that_accepts_a_token_signed_with_a_weak_key_gets_a_high_finding() -> None:
    rig = AuthzRig(Clinic(jwt=True, jwt_key="secret", lax="verify_hmac", check_exp=False))

    result = run_authz(rig, checks=(TAMPER,))

    findings = found(result, "authz_tampered_token")
    assert findings
    for finding in findings:
        assert finding.variants == ("weak_key", "weak_key_expired")
        assert finding.proposed_severity == "high"
        assert finding.cwe == 347
        assert "'secret'" not in finding.model_dump_json()


def test_a_short_weak_key_is_not_registered_for_masking_but_its_forged_token_is() -> None:
    rig = AuthzRig(Clinic(jwt=True, jwt_key="secret", lax="verify_hmac", check_exp=False))

    run_authz(rig, checks=(TAMPER,))

    assert rig.vault.mask("the secret word") == "the secret word"
    forged = [
        (header(r, "Authorization") or "").removeprefix("Bearer ")
        for r in sent(rig, "authz:tampered:")
    ]
    assert forged
    assert all(value not in rig.vault.mask(value) for value in forged)


def test_a_long_weak_key_is_registered_for_masking() -> None:
    rig = AuthzRig(Clinic(jwt=True, jwt_key="supersecret", lax="verify_hmac", check_exp=False))

    run_authz(rig, checks=(TAMPER,))

    assert "supersecret" not in rig.vault.mask("a supersecret word")


def test_a_server_that_checks_exp_accepts_only_the_weak_key_proof() -> None:
    rig = AuthzRig(Clinic(jwt=True, jwt_key="secret", lax="verify_hmac"))

    result = run_authz(rig, checks=(TAMPER,))

    findings = found(result, "authz_tampered_token")
    assert findings
    assert all(f.variants == ("weak_key",) for f in findings)


def test_weak_key_proof_requests_never_pass_five_per_operation() -> None:
    rig = AuthzRig(Clinic(jwt=True, jwt_key="secret", lax="verify_hmac", check_exp=False))

    run_authz(rig, checks=(TAMPER,))

    # 3 variantes comuns recusadas + no máximo 2 de prova por operação.
    assert max(tampered_by_operation(rig).values()) <= 5


def test_a_jwt_signed_with_a_strong_key_costs_only_the_common_variants() -> None:
    rig = AuthzRig(Clinic(jwt=True, jwt_key=STRONG_KEY, lax="verify_hmac"))

    result = run_authz(rig, checks=(TAMPER,))

    assert found(result, "authz_tampered_token") == []
    assert len(sent(rig, "authz:tampered:")) == 3 * summary(result, TAMPER).tested


def test_a_server_that_refuses_the_weak_key_proof_is_tested_without_finding() -> None:
    rig = AuthzRig(Clinic(jwt=True, jwt_key="secret"))

    result = run_authz(rig, checks=(TAMPER,))

    assert found(result, "authz_tampered_token") == []
    assert summary(result, TAMPER).tested >= 1


def test_the_per_run_cap_stops_weak_key_proofs_after_the_allowed_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(checks_access, "MAX_WEAK_KEY_OPERATIONS", 1)
    rig = AuthzRig(Clinic(jwt=True, jwt_key="secret", lax="verify_hmac", check_exp=False))

    result = run_authz(rig, checks=(TAMPER,))

    assert len(found(result, "authz_tampered_token")) == 1
