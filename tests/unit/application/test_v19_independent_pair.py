"""Regressões independentes do par criado na V1.9, sem alvo real."""

from __future__ import annotations

from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.probe_ports import FakeTarget, reply
from tests.fakes.rig import INT, STR, operation
from tests.unit.application.authz.test_created_pair import execute, make_rig


def test_v19_independent_server_generated_id_is_not_tested_without_proof() -> None:
    rig = make_rig("api/widgets", exposed=True)
    create = operation(
        "createSynthetic",
        "post",
        "/api/widgets",
        body={"label": STR},
        required=("label",),
        produces={"id": INT},
    )
    rig.spec = rig.spec.model_copy(
        update={
            "operations": tuple(
                create if item.operation_id == "createSynthetic" else item
                for item in rig.spec.operations
            )
        }
    )

    result = execute(rig, "api/widgets")

    assert not any(f.operation_id == "readSynthetic" for f in result.findings)
    assert any(n.reason == "new_identifier_unavailable" for n in result.not_tested)


def test_v19_independent_201_with_proven_new_id_and_owner_read() -> None:
    rig = make_rig("api/widgets", exposed=True)

    result = execute(rig, "api/widgets")

    assert any(f.operation_id == "readSynthetic" for f in result.findings)


def test_v19_independent_hidden_preexisting_resource_does_not_prove_creation() -> None:
    rig = make_rig("api/widgets", exposed=True)
    delegate = rig.clinic
    state = {"post_seen": False}

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        if request.operation_id == "authz:pair:createSynthetic":
            state["post_seen"] = True
            import json

            body = json.loads(request.body or b"{}")
            return reply(200, {"id": body["id"]})
        if request.operation_id == "authz:pair:readSynthetic":
            if not state["post_seen"]:
                return reply(404, {})  # recurso preexistente oculto da conta escritora
            key = request.url.rsplit("/", 1)[-1]
            return reply(200, {"id": key, "label": "preexisting"})
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        return response

    rig.target = FakeTarget(handler)
    result = execute(rig, "api/widgets")

    assert not any(f.operation_id == "readSynthetic" for f in result.findings)


def test_v19_independent_journal_failure_prevents_mutation() -> None:
    from typing import Literal

    from harness_dast.domain.errors import ConfigError
    from harness_dast.domain.mutation_snapshot import MutationSnapshot

    class UnavailableJournal:
        def begin(
            self,
            key: str,
            previous_state: Literal["absent", "present", "unknown"],
            snapshot: MutationSnapshot | None = None,
        ) -> None:
            raise ConfigError("diário indisponível")

        def finish(self, key: str, outcome: Literal["succeeded", "failed", "observed"]) -> None:
            raise AssertionError("não há resultado sem intenção")

    rig = make_rig("api/widgets", exposed=True)
    result = execute(rig, "api/widgets", journal=UnavailableJournal())

    assert result.status == "stopped_zap"
    assert any(n.reason == "mutation_outcome_unknown" for n in result.not_tested)
    assert not [
        request
        for request in rig.target.requests
        if request.operation_id == "authz:pair:createSynthetic"
    ]
