"""Caso de uso `probe`: ordem, pulos, dependências, parada antecipada e modo de simulação."""

from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

import pytest

from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import ConfigError, PreflightError, ScopeViolation, TargetTimeout
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.probe_result import ProbeResult
from tests.fakes.probe_ports import InMemoryDocuments, reply
from tests.fakes.rig import (
    ENV,
    STR,
    TOKEN,
    Rig,
    agenda_flows,
    agenda_profile,
    default_handler,
    operation,
    profile_data,
)


def run(rig: Rig, **changes: Any) -> ProbeResult:
    return rig.probe().execute(ProbeRequest(product="agenda", **changes))


def outcomes(result: ProbeResult) -> dict[str, str]:
    return {item.operation_id: item.outcome for item in result.operations}


def test_probe_runs_producers_before_consumers_and_chains_the_created_id() -> None:
    rig = Rig(flows=agenda_flows(), env=ENV)

    result = run(rig)

    paths = rig.target.paths()
    assert paths.index("/api/pacientes") < paths.index("/api/pacientes/7")
    assert outcomes(result)["buscar"] == "success"
    assert outcomes(result)["atualizar"] == "success"
    assert result.status == "completed"


def test_probe_classifies_skipped_scope_denied_and_destructive_without_sending_them() -> None:
    rig = Rig(flows=agenda_flows())

    result = run(rig)

    assert outcomes(result)["admin"] == "skipped_denied"
    assert outcomes(result)["externo"] == "skipped_scope"
    assert outcomes(result)["remover"] == "skipped_destructive"
    sent = " ".join(rig.target.paths())
    assert "admin" not in sent
    assert "outra" not in sent
    assert "DELETE" not in {r.method for r in rig.target.requests}


def test_reachability_divides_successes_by_attempted_and_by_all_operations() -> None:
    rig = Rig(flows=agenda_flows())

    summary = run(rig).summary

    assert summary.operations_total == 8
    assert summary.operations_sent == 5
    assert summary.successes == 5
    assert summary.reachability == 1.0
    assert summary.reachability_all == pytest.approx(0.625)


def test_dependents_are_skipped_when_their_producer_fails() -> None:
    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.method == "POST" and request.url.endswith("/api/pacientes"):
            return reply(400, {"message": "nome invalido"})
        return default_handler(request, jar)  # type: ignore[return-value]

    result = run(Rig(flows=agenda_flows(), handler=handler))

    assert outcomes(result)["criar"] == "validation_error"
    assert outcomes(result)["buscar"] == "skipped_dependency"
    assert outcomes(result)["atualizar"] == "skipped_dependency"
    assert result.summary.operations_sent == 3


def test_delete_runs_last_and_only_on_resources_created_in_this_run_when_included() -> None:
    rig = Rig(flows=agenda_flows())

    result = run(rig, include_delete=True)

    assert outcomes(result)["remover"] == "success"
    last = rig.target.requests[-1]
    assert last.method == "DELETE"
    assert last.url.endswith("/api/pacientes/7")


def test_delete_stays_skipped_when_it_is_not_fed_by_a_flow_even_if_included() -> None:
    rig = Rig(flows=None)

    result = run(rig, include_delete=True)

    item = next(i for i in result.operations if i.operation_id == "remover")
    assert item.outcome == "skipped_destructive"
    assert "flows.yml" in (item.message or "")
    assert all(r.method != "DELETE" for r in rig.target.requests)


def test_only_selects_operations_and_brings_their_producers() -> None:
    rig = Rig(flows=agenda_flows())

    result = run(rig, only=("buscar",))

    assert [i.operation_id for i in result.operations] == ["criar", "buscar"]


def test_only_with_unknown_operation_is_a_config_error() -> None:
    with pytest.raises(ConfigError):
        run(Rig(), only=("inexistente",))


def test_account_must_exist_in_the_profile() -> None:
    with pytest.raises(ConfigError) as info:
        run(Rig(), account="ninguem")

    assert "user_a" in (info.value.hint or "")


def test_build_error_tells_the_agent_which_rule_to_add() -> None:
    hard = Schema(type="string", pattern="^(?=a)b$")
    spec = ApiSpec(
        title="T",
        version="1",
        operations=(
            operation(
                "dificil", "post", "/api/dificil", body={"codigo": hard}, required=("codigo",)
            ),
        ),
    )

    result = run(Rig(spec=spec))

    item = result.operations[0]
    assert item.outcome == "build_error"
    assert "regra" in (item.hint or "").lower()
    assert result.summary.operations_sent == 0
    assert result.summary.reachability is None


def test_concrete_url_outside_scope_is_blocked_by_the_guard_and_never_sent() -> None:
    spec = ApiSpec(
        title="T",
        version="1",
        operations=(
            operation("tentativa", "get", "/api/coisas/{nome}", parameters=(_text_param(),)),
        ),
    )
    from tests.unit.api_helpers import rule, rules_from

    rules = rules_from(rule("nome", "constant", value=".."))
    rig = Rig(spec=spec, rules=rules)

    result = run(rig)

    item = result.operations[0]
    assert item.outcome == "skipped_scope"
    assert all("coisas" not in r.url for r in rig.target.requests)
    denied = [e for e in rig.store.all_audit() if e.decision == "denied"]
    assert len(denied) == 1
    assert not [e for e in rig.store.all_audit() if e.phase == "result" and e.seq == denied[0].seq]


def _text_param() -> Any:
    from tests.fakes.rig import parameter

    return parameter("nome", STR)


def test_window_closing_mid_run_stops_the_probe_with_a_partial_result() -> None:
    data = profile_data()
    data["scope"]["windows"] = ["seg-dom 12:00-12:30 UTC"]
    rig = Rig(profile=agenda_profile(**{"scope": data["scope"]}), flows=agenda_flows())

    def closing(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.url.endswith("/api/pacientes") and request.method == "GET":
            rig.clock.advance(31 * 60)
        return default_handler(request, jar)  # type: ignore[return-value]

    rig.target._handler = closing

    result = run(rig)

    assert result.status == "stopped_window"
    assert "janela" in (result.stop_message or "").lower()
    assert len(result.operations) < result.summary.operations_total
    assert rig.store.probes[result.run_id].status == "stopped_window"
    assert rig.store.manifests[result.run_id][-1].status == "stopped_window"


def test_max_duration_stops_the_probe_even_inside_the_window() -> None:
    data = profile_data()
    data["limits"]["max_duration_minutes"] = 1
    rig = Rig(profile=agenda_profile(limits=data["limits"]), flows=agenda_flows())

    def slow(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        rig.clock.advance(61)
        return default_handler(request, jar)  # type: ignore[return-value]

    rig.target._handler = slow

    result = run(rig)

    assert result.status == "stopped_deadline"
    assert "tempo máximo" in (result.stop_message or "")


def test_probe_refuses_to_start_when_the_window_is_closed_now() -> None:
    data = profile_data()
    data["scope"]["windows"] = ["seg-dom 20:00-21:00 UTC"]
    rig = Rig(profile=agenda_profile(scope=data["scope"]))

    with pytest.raises(ScopeViolation):
        run(rig)

    assert rig.target.requests == []
    assert rig.zap.sessions == []


def test_probe_refuses_to_start_when_the_authorization_expired() -> None:
    data = profile_data()
    data["scope"]["authorization"]["valid_until"] = "2020-01-01"
    rig = Rig(profile=agenda_profile(scope=data["scope"]))

    with pytest.raises(ScopeViolation):
        run(rig)

    assert rig.target.requests == []


def test_five_timeouts_in_a_row_stop_the_probe_as_unresponsive() -> None:
    def hanging(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        return TargetTimeout("sem resposta")

    spec = ApiSpec(
        title="T",
        version="1",
        operations=tuple(operation(f"op{i}", "get", f"/api/r{i}") for i in range(8)),
    )

    result = run(Rig(spec=spec, handler=hanging))

    assert result.status == "stopped_target_unresponsive"
    assert [i.outcome for i in result.operations] == ["timeout"] * 5


def test_a_success_between_failures_resets_the_unresponsive_counter() -> None:
    state = {"n": 0}

    def flaky(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        state["n"] += 1
        return TargetTimeout("x") if state["n"] % 3 else reply(200, {})

    spec = ApiSpec(
        title="T",
        version="1",
        operations=tuple(operation(f"op{i}", "get", f"/api/r{i}") for i in range(9)),
    )

    result = run(Rig(spec=spec, handler=flaky))

    assert result.status == "completed"


def test_zap_failing_at_start_is_a_preflight_error_and_sends_nothing() -> None:
    from harness_dast.domain.errors import ExternalToolError

    rig = Rig()
    rig.zap.fail = ExternalToolError("ZAP fora", hint="suba o ZAP")

    with pytest.raises(PreflightError) as info:
        run(rig)

    assert "ZAP" in info.value.message
    assert rig.target.requests == []


def test_proxy_failure_mid_run_stops_the_probe_as_zap_error() -> None:
    from harness_dast.domain.errors import ExternalToolError

    def broken(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        return ExternalToolError("proxy caiu")

    result = run(Rig(handler=broken))

    assert result.status == "stopped_zap"
    assert result.stop_message == "proxy caiu"


def test_session_is_prepared_with_a_context_limited_to_the_scope_and_stale_rules_removed() -> None:
    rig = Rig()

    result = run(rig)

    assert rig.zap.sessions == [f"hdast-{result.run_id}"]
    name, include, exclude = rig.zap.contexts[0]
    assert name == f"hdast-{result.run_id}"
    assert any("api\\.hml\\.acme\\-teste\\.net\\.br" in regex for regex in include)
    assert any("admin" in regex for regex in exclude)
    assert rig.zap.removed_prefixes == ["hdast-"]
    assert "outra-regra" in rig.zap.rules
    assert "hdast-auth" not in rig.zap.rules


def test_manifest_records_run_context_hashes_limits_and_seed() -> None:
    rig = Rig()

    result = run(rig, seed=42)

    first, last = rig.store.manifests[result.run_id][0], rig.store.manifests[result.run_id][-1]
    assert first.status == "running"
    assert first.finished_at is None
    assert last.status == "completed"
    assert last.finished_at is not None
    assert last.seed == 42
    assert last.zap_version == "2.17.0"
    assert last.zap_context_id == 1
    assert last.hashes.target_yml == "a" * 64
    assert last.limits.requests_per_second == 5
    assert last.accounts == ("user_a",)
    assert last.harness_version == "0.0-test"


def test_run_id_is_built_from_the_injected_clock_and_randomness() -> None:
    result = run(Rig())

    assert result.run_id == "2026-11-10T12-00-00Z-agenda-7f3a"


def test_same_seed_gives_the_same_requests_and_another_seed_changes_them() -> None:
    def bodies(seed: int) -> list[bytes | None]:
        rig = Rig(flows=agenda_flows())
        run(rig, seed=seed)
        return [r.body for r in rig.target.requests]

    assert bodies(5) == bodies(5)
    assert bodies(5) != bodies(6)


def test_requests_are_paced_by_the_profile_rate() -> None:
    data = profile_data()
    data["limits"]["requests_per_second"] = 2
    rig = Rig(profile=agenda_profile(limits=data["limits"]))
    stamps: list[datetime] = []

    def stamped(request: HttpRequest, jar: dict[str, str]) -> Any:
        stamps.append(rig.clock.now())
        return default_handler(request, jar)

    rig.target._handler = stamped

    run(rig)

    gaps = [(b - a).total_seconds() for a, b in pairwise(stamps)]
    assert gaps
    assert all(gap >= 0.5 - 1e-6 for gap in gaps)


def test_redirect_is_reported_and_never_followed() -> None:
    def redirecting(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        return reply(302, None, location="https://outro.example.org/x")

    spec = ApiSpec(title="T", version="1", operations=(operation("sai", "get", "/api/sai"),))
    rig = Rig(spec=spec, handler=redirecting)

    result = run(rig)

    item = result.operations[0]
    assert item.outcome == "redirect"
    assert item.redirect_in_scope is False
    assert item.untrusted_target_data is not None
    assert len(rig.target.requests) == 2  # o login e a própria operação, nada além


def test_dry_run_sends_nothing_and_writes_nothing_but_reports_what_would_be_sent() -> None:
    rig = Rig(flows=agenda_flows())

    result = run(rig, dry_run=True)

    assert rig.target.requests == []
    assert rig.zap.sessions == []
    assert rig.store.events == []
    assert result.dry_run is True
    by_id = {i.operation_id: i for i in result.operations}
    assert by_id["criar"].outcome == "dry_run"
    preview = by_id["criar"].preview
    assert preview is not None
    assert [(f.name, f.generator) for f in preview.fields] == [("body.nome", "alphanumeric")]
    assert by_id["buscar"].preview is not None
    assert by_id["buscar"].preview.uses_flow_values is True
    assert by_id["admin"].outcome == "skipped_denied"
    assert result.summary.reachability is None


def test_dry_run_never_shows_generated_values() -> None:
    rig = Rig(flows=agenda_flows())

    result = run(rig, dry_run=True, seed=3)

    real = Rig(flows=agenda_flows())
    run(real, seed=3)
    values = [r.body.decode() for r in real.target.requests if r.body and b"nome" in r.body]
    assert values
    for value in values:
        generated = value.split('"nome":"')[1].split('"')[0]
        assert generated not in result.model_dump_json()


def test_missing_secret_is_a_preflight_error_that_names_account_and_field_only() -> None:
    rig = Rig(env={"ACME_USER_A_LOGIN": "alice"})

    with pytest.raises(PreflightError) as info:
        run(rig)

    assert "user_a.password" in info.value.message
    assert "ACME_USER_A_SENHA" not in info.value.message + (info.value.hint or "")


def test_rejected_login_is_a_preflight_error_and_the_manifest_is_closed() -> None:
    def refusing(request: HttpRequest, jar: dict[str, str]) -> Any:
        return reply(401, {"detail": "credenciais"})

    rig = Rig(handler=refusing)

    with pytest.raises(PreflightError):
        run(rig)

    run_id = next(iter(rig.store.manifests))
    assert rig.store.manifests[run_id][-1].status == "failed_start"
    assert run_id not in rig.store.probes


def test_data_rules_and_flows_must_match_the_openapi() -> None:
    bad = InMemoryDocuments(flows=_flows_with_unknown_operation())
    rig = Rig(documents=bad)

    with pytest.raises(ConfigError):
        run(rig)


def _flows_with_unknown_operation() -> Any:
    from harness_dast.domain.flow import FlowSpec

    return FlowSpec.from_data(
        {
            "schema_version": 1,
            "bindings": [
                {
                    "produces": {"operation": "fantasma", "field": "id"},
                    "consumed_by": [{"operation": "buscar", "param": "pacienteId"}],
                }
            ],
        }
    )


def test_started_at_uses_the_injected_clock() -> None:
    result = run(Rig())

    assert result.started_at == datetime(2026, 11, 10, 12, 0, tzinfo=UTC).isoformat()
