"""Revisão independente da leitura de um único recurso criado."""

import json
from typing import Literal

import pytest

from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from tests.fakes.probe_ports import FakeTarget, reply
from tests.unit.application.authz.test_created_pair import execute, make_rig


@pytest.mark.parametrize("shape", ["empty", "multiple", "wrong", "ambiguous", "duplicate"])
def test_v19_independent_array_must_identify_exactly_created_resource(
    shape: Literal["empty", "multiple", "wrong", "ambiguous", "duplicate"],
) -> None:
    rig = make_rig("api/widgets", exposed=True)
    delegate = rig.clinic

    def handler(request: HttpRequest, jar: dict[str, str]) -> HttpResponse:
        response = delegate(request, jar)
        assert isinstance(response, HttpResponse)
        if request.operation_id != "authz:pair:readSynthetic" or response.status != 200:
            return response
        item = json.loads(response.body)
        if shape == "empty":
            return reply(200, [])
        if shape == "multiple":
            return reply(200, [item, item])
        if shape == "wrong":
            return reply(200, [{**item, "id": "other"}])
        if shape == "ambiguous":
            return reply(200, [{**item, "ID": "other"}])
        raw = json.dumps([item]).replace("{", '{"id":"other",', 1).encode()
        return response.model_copy(update={"body": raw})

    rig.target = FakeTarget(handler)
    result = execute(rig, "api/widgets")

    assert not any(f.operation_id == "readSynthetic" for f in result.findings)
    assert any(n.reason == "created_read_ambiguous" for n in result.not_tested)


def test_v19_independent_no_pair_post_when_writes_not_authorized() -> None:
    rig = make_rig("api/widgets", exposed=True, allow_writes=False)
    result = execute(rig, "api/widgets")
    assert any(n.reason == "writes_not_authorized" for n in result.not_tested)
    assert not [r for r in rig.target.requests if r.operation_id == "authz:pair:createSynthetic"]


def test_v19_independent_marker_is_not_in_result_or_audit() -> None:
    rig = make_rig("api/widgets", exposed=True)
    result = execute(rig, "api/widgets")
    post = next(r for r in rig.target.requests if r.operation_id == "authz:pair:createSynthetic")
    marker = json.loads(post.body or b"{}")["label"]
    assert result.findings
    assert marker not in result.model_dump_json()
    assert marker not in rig.store.serialized()
