"""QA independente (V1.5c): `error-signals.json` a partir de linhas de auditoria hostis."""

from datetime import UTC, datetime, timedelta

import pytest

from harness_dast.domain.finding_build import AlertResolver
from harness_dast.domain.signal_findings import build_proxy_signals, signal_fingerprint
from harness_dast.domain.signal_result import MAX_SIGNAL_FINDINGS, MAX_STATUSES
from harness_dast.domain.traffic import ProxyRow

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
WINDOW = (T0, T0 + timedelta(minutes=10))


class NoOperations:
    """Resolvedor que não reconhece nenhum caminho (pior caso: o caminho concreto sobra)."""

    def resolve_path(self, method: str, path: str) -> None:
        return None


RESOLVER: AlertResolver = NoOperations()  # type: ignore[assignment]  # só `resolve_path` é usado


def row(
    path: str = "/api/x",
    *,
    signals: tuple[str, ...] = ("sql_error",),
    status: int | None = 500,
    decision: str = "allow",
    at: datetime = T0 + timedelta(minutes=1),
    method: str = "GET",
    skip: str | None = None,
    params: tuple[str, ...] = (),
) -> ProxyRow:
    return ProxyRow.model_validate(
        {
            "at": at,
            "decision": decision,
            "reason": "allowed",
            "method": method,
            "path": path,
            "status": status,
            "signals": signals,
            "signal_skip": skip,
            "query_params": params,
        }
    )


def build(*rows: ProxyRow):  # type: ignore[no-untyped-def]  # auxiliar de teste
    return build_proxy_signals(rows, product="demo", window=WINDOW, resolver=RESOLVER)


def test_a_concrete_secret_segment_never_reaches_the_path_template_of_a_finding() -> None:
    secret = "tok-SEGREDO-9f8e7d6c5b4a"  # noqa: S105 - sentinela de teste
    result = build(row(f"/api/users/{secret}/profile"))

    text = result.model_dump_json()
    assert result.findings
    assert secret not in text


@pytest.mark.parametrize(
    "path",
    [
        "/api/users/12345/orders/67890",
        "/api/users/3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        "/api/files/ZXhhbXBsZS10b2tlbi1zZWNyZXRv",
    ],
)
def test_identifiers_in_unresolved_paths_are_generalised(path: str) -> None:
    result = build(row(path))
    template = result.findings[0].path_template

    last = path.rsplit("/", 1)[-1]
    assert last not in template


@pytest.mark.parametrize("path", ["/api/u/maria.silva@example.com", "/api/cpf/123.456.789-09"])
def test_personal_identifiers_in_unresolved_paths_are_generalised(path: str) -> None:
    result = build(row(path))

    assert path.rsplit("/", 1)[-1] not in result.findings[0].path_template


def test_rows_outside_the_window_denied_or_without_status_never_count() -> None:
    result = build(
        row(at=T0 - timedelta(seconds=1)),
        row(at=T0 + timedelta(minutes=11)),
        row(decision="deny"),
        row(status=None),
    )

    assert result.responses_examined == 0
    assert result.findings == ()
    assert result.responses_with_signal == 0


def test_the_window_edges_are_inclusive() -> None:
    result = build(row(at=WINDOW[0]), row(at=WINDOW[1], path="/api/y"))

    assert result.responses_examined == 2


def test_unknown_signal_names_in_the_audit_are_ignored_not_trusted() -> None:
    result = build(row(signals=("sql_error_x", "<script>", "", "debug_page")))

    assert [finding.category for finding in result.findings] == ["debug_page"]
    assert set(result.counts) >= {"sql_error", "debug_page"}
    assert all(name.isidentifier() for name in result.counts)


def test_a_row_with_signals_and_a_skip_reason_counts_as_skipped_only() -> None:
    result = build(row(skip="encoding"))

    assert result.responses_skipped == {"encoding": 1}
    assert result.responses_examined == 0
    assert result.responses_with_signal == 0
    assert result.findings == ()


def test_examined_plus_skipped_is_always_the_number_of_allowed_rows_in_the_window() -> None:
    rows = [
        row("/a"),
        row("/b", signals=(), skip="type"),
        row("/c", signals=(), skip="empty"),
        row("/d", signals=()),
        row("/e", decision="deny"),
    ]

    result = build(*rows)

    assert result.responses_examined + sum(result.responses_skipped.values()) == 4


def test_the_findings_are_capped_and_the_overflow_is_counted_with_exact_totals() -> None:
    rows = [row(f"/api/r{index}/x") for index in range(MAX_SIGNAL_FINDINGS + 25)]

    result = build(*rows)

    assert len(result.findings) <= MAX_SIGNAL_FINDINGS
    assert len(result.findings) + result.findings_omitted >= MAX_SIGNAL_FINDINGS + 1
    assert result.counts["sql_error"] == len(rows)


def test_statuses_are_capped_and_distinct() -> None:
    rows = [row(status=500 + index) for index in range(20)]

    result = build(*rows)

    assert len(result.findings[0].statuses) <= MAX_STATUSES
    assert len(set(result.findings[0].statuses)) == len(result.findings[0].statuses)


def test_the_query_parameter_names_are_capped_and_never_carry_values() -> None:
    names = tuple(f"p{index}" for index in range(40))

    result = build(row(params=names))

    assert len(result.findings[0].query_params) <= 10
    assert "=" not in "".join(result.findings[0].query_params)


def test_the_fingerprint_ignores_case_of_method_and_status_but_not_category_or_product() -> None:
    first = signal_fingerprint(
        product="p", method="get", path_template="/a/{id}", category="sql_error"
    )
    same = signal_fingerprint(
        product="p", method="GET", path_template="/a/{id}", category="sql_error"
    )
    other_category = signal_fingerprint(
        product="p", method="GET", path_template="/a/{id}", category="debug_page"
    )
    other_product = signal_fingerprint(
        product="q", method="GET", path_template="/a/{id}", category="sql_error"
    )

    assert first == same
    assert len({first, other_category, other_product}) == 3


def test_fields_that_could_collide_by_concatenation_do_not_collide() -> None:
    one = signal_fingerprint(product="ab", method="GET", path_template="/c", category="sql_error")
    two = signal_fingerprint(product="a", method="GET", path_template="b/c", category="sql_error")

    assert one != two
