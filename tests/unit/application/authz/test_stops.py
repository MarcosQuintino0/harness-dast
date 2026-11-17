"""`authz`: paradas antecipadas e respostas inconclusivas (nunca viram "seguro")."""

from datetime import timedelta
from typing import Any

from harness_dast.application.authz.service import AuthzRequest
from harness_dast.domain.errors import ExternalToolError
from tests.fakes.authz.rig import AuthzRig, Clinic
from tests.fakes.probe_ports import reply


def after_probe(rig: AuthzRig, behaviour: Any) -> str:
    """Roda o `probe` normalmente e só depois troca o comportamento do alvo falso."""
    run_id = rig.run_probe().run_id
    rig.clinic._route = behaviour  # type: ignore[method-assign]  # troca o comportamento do falso
    return run_id


def summary(result: Any, name: str) -> Any:
    return next(item for item in result.checks if item.check == name)


def test_a_target_that_stops_answering_ends_the_stage_with_a_partial_result() -> None:
    rig = AuthzRig(Clinic(bola=True))
    run_id = after_probe(rig, lambda request, path, alias: reply(503, {}))

    result = rig.authz().execute(AuthzRequest(product="agenda", run_id=run_id))

    assert result.status == "stopped_target_unresponsive"
    assert "sem resposta" in (result.stop_message or "")
    assert result.findings == ()
    assert rig.artifacts.authz[run_id] == result


def test_a_proxy_failure_ends_the_stage_as_stopped_zap() -> None:
    rig = AuthzRig(Clinic(bola=True))
    run_id = rig.run_probe().run_id
    original = rig.target._handler

    def broken(request: Any, jar: Any) -> Any:
        if request.operation_id.startswith("authz:"):
            return ExternalToolError("O proxy do ZAP não respondeu.")
        return original(request, jar)

    rig.target._handler = broken

    result = rig.authz().execute(AuthzRequest(product="agenda", run_id=run_id))

    assert result.status == "stopped_zap"


def test_an_exhausted_deadline_ends_the_stage_before_any_request() -> None:
    rig = AuthzRig(Clinic(bola=True))
    run_id = rig.run_probe().run_id
    sent = len(rig.target.requests)

    result = rig.authz().execute(
        AuthzRequest(
            product="agenda", run_id=run_id, deadline=rig.clock.now() - timedelta(seconds=1)
        )
    )

    assert result.status == "stopped_deadline"
    assert len(rig.target.requests) == sent
    assert {c.status for c in result.checks} <= {"skipped", "disabled"}


def test_a_single_server_error_is_inconclusive_never_safe() -> None:
    rig = AuthzRig(Clinic(bola=True))
    original = rig.clinic._route

    def flaky(request: Any, path: str, alias: str) -> Any:
        if alias == "pac_b" and path.startswith("api/consultas/"):
            return reply(500, {})
        return original(request, path, alias)

    run_id = after_probe(rig, flaky)

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=run_id, checks=("horizontal",))
    )

    assert result.findings == ()
    assert any(n.reason == "inconclusive" for n in result.not_tested)
    assert summary(result, "horizontal").status == "skipped"


def test_a_vertical_4xx_other_than_401_and_403_is_inconclusive() -> None:
    rig = AuthzRig(Clinic(bfla=False))
    run_id = after_probe(rig, lambda request, path, alias: reply(404, {}))

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=run_id, checks=("vertical",))
    )

    assert result.findings == ()
    assert "inconclusive" in {n.reason for n in result.not_tested if n.check == "vertical"}
    assert summary(result, "vertical").tested == 0


def test_excessive_data_without_a_declared_response_schema_is_not_tested() -> None:
    rig = AuthzRig(Clinic(excess=True))
    rig.spec = rig.spec.model_copy(
        update={
            "operations": tuple(
                op.model_copy(update={"success_responses": ()}) for op in rig.spec.operations
            )
        }
    )
    run_id = rig.run_probe().run_id

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=run_id, checks=("excessive_data",))
    )

    assert result.findings == ()
    assert {n.reason for n in result.not_tested} == {"no_response_schema"}


def test_a_non_json_success_response_is_not_compared_with_the_schema() -> None:
    rig = AuthzRig(Clinic())
    original = rig.clinic._route

    def plain(request: Any, path: str, alias: str) -> Any:
        if path == "api/pacientes":
            return reply(200, b"texto simples", content_type="text/plain")
        return original(request, path, alias)

    run_id = after_probe(rig, plain)

    result = rig.authz().execute(
        AuthzRequest(product="agenda", run_id=run_id, checks=("excessive_data",))
    )

    assert any(
        n.reason == "no_json_response" and n.operation_id == "listarPacientes"
        for n in result.not_tested
    )
