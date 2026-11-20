"""Restrições independentes do campo usado como marcador sintético."""

import pytest

from harness_dast.domain.api_schema import Schema
from harness_dast.domain.authz.pair_marker import marker_fields
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.request_builder import RequestBuilder
from tests.fakes.rig import STR, operation, parameter


@pytest.mark.parametrize(
    ("name", "schema", "bound", "credentials"),
    [
        ("passphrase", STR, frozenset(), frozenset({"PASS_PHRASE"})),
        ("field", Schema(type="string", read_only=True), frozenset(), frozenset()),
        ("field", Schema(type="string", format="password"), frozenset(), frozenset()),
        ("field", Schema(type="string", pattern="x+"), frozenset(), frozenset()),
        ("role", STR, frozenset(), frozenset()),
        ("foreign", STR, frozenset({"foreign"}), frozenset()),
    ],
)
def test_v19_independent_marker_rejects_protected_field(
    name: str, schema: Schema, bound: frozenset[str], credentials: frozenset[str]
) -> None:
    fields = {name: schema}
    post = operation("create", "post", "/items", body=fields)
    read = operation("read", "get", "/items/{id}", parameters=(parameter("id"),), produces=fields)
    assert marker_fields(post, read, bound, credentials) == ()


def test_v19_independent_constant_rule_is_not_overwritten_as_marker() -> None:
    rules = DataRules.from_data(
        {
            "schema_version": 1,
            "rules": [
                {"match": {"field": "note"}, "generator": "constant", "args": {"value": "fixed"}}
            ],
        }
    )
    builder = RequestBuilder(rules, lambda request: "fixed", "abcd")
    assert builder.body_rule_marker_eligible("create", "note") is False
