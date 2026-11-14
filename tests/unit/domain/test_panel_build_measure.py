"""Medição do painel: tokens do agente (tolerante) e correspondência com as etapas da CLI."""

import pytest
from pydantic import ValidationError

from harness_dast.domain.agent_metrics import (
    AgentMetrics,
    AgentStageMetrics,
    AgentTokens,
    AgentTotals,
)
from harness_dast.domain.panel_build_measure import (
    OTHER_TOKENS,
    build_measurements,
    with_stage_tokens,
)
from tests.unit.domain.panel_helpers import view
from tests.unit.domain.panel_measure_helpers import agent_metrics, measured_view, run_metrics


def test_tokens_count_input_output_and_cache_written_but_not_cache_read() -> None:
    tokens = AgentTokens(input=1, output=2, cache_creation=3, cache_read=1000)

    assert tokens.counted == 6


def test_the_agent_file_ignores_unknown_fields_and_misses_become_none() -> None:
    loaded = AgentMetrics.model_validate(
        {"schema_version": 1, "campo_novo": 1, "totals": {"duration_seconds": 5}, "stages": {}}
    )

    assert loaded.model is None
    assert loaded.totals is not None
    assert loaded.totals.tokens is None


@pytest.mark.parametrize(
    "bad",
    [
        {"schema_version": 1, "totals": {"tokens": {"input": -1}}},
        {"schema_version": 1, "totals": {"tokens": {"input": "muito"}}},
        {"schema_version": "um"},
        {"totals": {}},
    ],
)
def test_a_malformed_agent_file_is_rejected_by_the_model(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentMetrics.model_validate(bad)


def test_without_the_agent_file_every_token_field_is_none() -> None:
    measurements = build_measurements(run_metrics(), None)

    assert measurements.metrics_available
    assert measurements.tokens_total is None
    assert measurements.tokens_by_stage is None
    assert measurements.tokens_breakdown is None
    assert measurements.agent_model is None


def test_the_agent_stages_map_to_the_cli_stages() -> None:
    measurements = build_measurements(None, agent_metrics())

    assert measurements.tokens_by_stage == {
        "preflight": (4 + 247 + 61359) + (20 + 5788 + 43436),
        "probe": 18 + 3774 + 8554,
        "scan": 28 + 3009 + 13589,
        "report": 10 + 4970 + 20062,
        OTHER_TOKENS: 2 + 1250 + 1841,
    }
    assert not measurements.metrics_available


def test_an_unknown_agent_stage_goes_to_other_and_a_stage_without_tokens_is_left_out() -> None:
    agent = AgentMetrics(
        schema_version=1,
        stages={
            "etapa-nova": AgentStageMetrics(tokens=AgentTokens(input=7)),
            "alcance": AgentStageMetrics(),
        },
    )

    assert build_measurements(None, agent).tokens_by_stage == {OTHER_TOKENS: 7}


def test_a_file_with_no_tokens_at_all_keeps_the_dash() -> None:
    agent = AgentMetrics(schema_version=1, totals=AgentTotals(), stages={})

    measurements = build_measurements(None, agent)

    assert measurements.tokens_total is None
    assert measurements.tokens_by_stage is None


def test_the_total_and_the_split_come_from_the_totals() -> None:
    measurements = build_measurements(None, agent_metrics())

    assert measurements.tokens_total == 82 + 19038 + 148841
    assert measurements.tokens_breakdown is not None
    assert measurements.tokens_breakdown.cache_read == 4469981
    assert measurements.agent_model == "claude-sonnet-5-5"


def test_the_view_puts_the_tokens_on_the_stages() -> None:
    stages = {item.key: item.tokens for item in measured_view().stages}

    assert stages["probe"] == 18 + 3774 + 8554
    assert stages["authz"] is None


def test_without_the_agent_file_the_stages_keep_none() -> None:
    assert all(item.tokens is None for item in view().stages)
    assert with_stage_tokens(view().stages, None) == view().stages
