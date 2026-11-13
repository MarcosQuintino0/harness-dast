"""`scope.path_mode` no perfil e o que `scan.json` e `report.md` dizem sobre ele (ADR 0026)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.report_markdown import render_markdown
from harness_dast.domain.traffic import (
    ProxyRow,
    TrafficSummary,
    path_shape_breakdown,
    summarize_traffic,
)
from tests.fakes.profile_data import valid_profile_data
from tests.unit.domain.test_report_markdown import report

T0 = datetime(2026, 11, 13, 10, 0, 0, tzinfo=UTC)


def _profile_with(value: object, *, present: bool = True) -> Any:
    data = valid_profile_data()
    if present:
        data["scope"]["path_mode"] = value
    return ProductProfile.from_data(data)


# ------------------------------------------------------------------- perfil


def test_profile_defaults_to_strict_when_path_mode_is_absent() -> None:
    assert _profile_with(None, present=False).scope.path_mode == "strict"


@pytest.mark.parametrize("value", ["strict", "wide"])
def test_profile_accepts_the_two_modes(value: str) -> None:
    assert _profile_with(value).scope.path_mode == value


@pytest.mark.parametrize(
    "value",
    ["Wide", "WIDE", "amplo", "", " wide", None, 1, 0, True, ["wide"], {"mode": "wide"}],
)
def test_profile_rejects_an_invalid_path_mode(value: object) -> None:
    with pytest.raises(ConfigError, match="path_mode"):
        _profile_with(value)


def test_to_scope_does_not_carry_the_mode_to_the_guard() -> None:
    scope = _profile_with("wide").scope.to_scope()

    assert not hasattr(scope, "path_mode")


# ------------------------------------------------------------------ tráfego


def _row(offset: float, decision: str, reason: str, detail: str | None = None) -> ProxyRow:
    return ProxyRow(
        at=T0 + timedelta(seconds=offset),
        decision=decision,
        reason=reason,
        method="GET",
        detail=detail,
    )


def test_summary_counts_denials_by_granular_detail_and_path_shape() -> None:
    rows = [
        _row(0, "allow", "allowed"),
        _row(1, "deny", "malformed_request", "path_encoded_slash"),
        _row(2, "deny", "malformed_request", "path_encoded_slash"),
        _row(3, "deny", "malformed_request", "path_matrix_param"),
        _row(4, "deny", "malformed_request", "url_forbidden_char"),
        _row(5, "deny", "deny_path"),
        _row(6, "deny", "malformed_request"),  # linha antiga, sem detalhe
    ]

    summary = summarize_traffic(rows, start=T0, end=T0 + timedelta(seconds=10), limit_rps=5)

    assert summary.denied_by_reason == {"malformed_request": 5, "deny_path": 1}
    assert summary.denied_by_detail == {
        "path_encoded_slash": 2,
        "path_matrix_param": 1,
        "url_forbidden_char": 1,
        "deny_path": 1,
        "malformed_request": 1,
    }
    assert summary.path_shape_denied == 3
    assert path_shape_breakdown(summary) == {"path_encoded_slash": 2, "path_matrix_param": 1}


def test_summary_counts_releases_with_a_reading_outside_allow_and_records_the_mode() -> None:
    rows = [
        _row(0, "allow", "allowed"),
        _row(1, "allow", "allowed", "wide_reading_outside_allow"),
        _row(2, "allow", "allowed", "wide_reading_outside_allow"),
    ]

    summary = summarize_traffic(
        rows, start=T0, end=T0 + timedelta(seconds=10), limit_rps=5, path_mode="wide"
    )

    assert (summary.allowed, summary.allowed_outside_allow, summary.path_mode) == (3, 2, "wide")


def test_summary_defaults_to_strict_mode() -> None:
    assert summarize_traffic([], start=T0, end=T0, limit_rps=5).path_mode == "strict"


def test_summary_ignores_the_detail_of_rows_outside_the_interval() -> None:
    rows = [_row(-5, "deny", "malformed_request", "path_matrix_param")]

    summary = summarize_traffic(rows, start=T0, end=T0 + timedelta(seconds=10), limit_rps=5)

    assert summary.path_shape_denied == 0


# ---------------------------------------------------------------- relatório


def _text(traffic: TrafficSummary) -> str:
    base = report([])
    measured = base.model_copy(
        update={"coverage": base.coverage.model_copy(update={"traffic": traffic})}
    )
    return render_markdown(measured)


def _traffic(**changes: Any) -> TrafficSummary:
    data: dict[str, Any] = {
        "enabled": True,
        "allowed": 40,
        "denied": 60,
        "denied_by_reason": {"malformed_request": 60},
        "denied_by_detail": {
            "path_encoded_slash": 30,
            "path_matrix_param": 20,
            "url_not_ascii": 10,
        },
        "path_shape_denied": 50,
        "duration_seconds": 60.0,
        "average_rps": 1.0,
        "peak_rps": 2,
        "limit_rps": 5.0,
    }
    data.update(changes)
    return TrafficSummary.model_validate(data)


def test_report_warns_that_path_injection_coverage_was_partial() -> None:
    text = _text(_traffic())

    assert "cobertura de injeção em segmento de caminho foi PARCIAL" in text
    assert "50 de 100 pedido(s) (50%)" in text
    assert r"path\_encoded\_slash: 30" in text
    assert r"path\_matrix\_param: 20" in text
    assert "url_not_ascii" not in text  # forma da URL, não do caminho
    assert "Modo de leitura do caminho no proxy: strict" in text
    assert "só o dono do produto pode autorizar `wide` na carta" in text


def test_report_has_no_partial_coverage_warning_when_no_path_was_refused() -> None:
    text = _text(_traffic(denied=0, denied_by_reason={}, denied_by_detail={}, path_shape_denied=0))

    assert "PARCIAL" not in text
    assert "Modo de leitura do caminho no proxy: strict" in text


def test_report_in_wide_mode_states_the_mode_and_counts_releases_outside_allow() -> None:
    text = _text(_traffic(path_mode="wide", allowed_outside_allow=7))

    assert "Modo de leitura do caminho no proxy: wide" in text
    assert "7 pedido(s) liberados têm uma leitura do caminho fora de `scope.allow`" in text
    assert "só o dono do produto" not in text


def test_report_strict_mode_does_not_mention_releases_outside_allow() -> None:
    assert "fora de `scope.allow`" not in _text(_traffic())
