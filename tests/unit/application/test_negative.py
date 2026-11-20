"""`negative`: o estágio lê por padrão, classifica a reação e nunca grava o valor enviado."""

from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

from harness_dast.application.negative import NegativeRequest
from harness_dast.domain.errors import ConfigError, ExternalToolError
from tests.fakes.negative_rig import (
    ADJUST,
    CREATE,
    LIST,
    REMOVE,
    SENT_MARKERS,
    UPDATE,
    Catalog,
    NegativeRig,
)


def reasons(result: Any) -> list[str]:
    return [item.reason for item in result.not_tested]


def sent_queries(rig: NegativeRig) -> list[dict[str, str]]:
    return [dict(parse_qsl(urlsplit(r.url).query)) for r in rig.sent("GET")]


def test_by_default_only_reads_are_sent_and_the_rejections_are_not_findings() -> None:
    rig = NegativeRig(Catalog(mode="validate"))

    result = rig.run(LIST, CREATE, UPDATE, ADJUST)

    assert result.status == "completed"
    assert result.findings == ()
    assert {r.method for r in rig.sent()} == {"GET"}
    assert result.requests_sent == len(rig.sent())
    summary = {row.case_class: row for row in result.by_class}
    assert summary["wrong_type"].rejected == 1
    assert summary["not_in_enum"].rejected == 1
    assert sum(row.sent for row in result.by_class) == len(rig.sent())
    assert result.operations_tested == 1
    assert rig.artifacts.negative[result.run_id] == result


def test_writes_without_the_letter_are_reported_and_nothing_is_sent_for_them() -> None:
    rig = NegativeRig(Catalog(mode="validate"))

    result = rig.run(CREATE, UPDATE, ADJUST)

    blocked = [n for n in result.not_tested if n.reason == "writes_not_authorized"]
    assert {n.operation_id for n in blocked} == {
        "criarProduto",
        "atualizarProduto",
        "ajustarProduto",
    }
    assert "negative.allow_writes" in blocked[0].message
    assert rig.sent() == []
    assert result.requests_sent == 0


def test_a_server_that_accepts_the_forbidden_value_yields_one_low_finding_per_field() -> None:
    rig = NegativeRig(Catalog(mode="lax"))

    result = rig.run(LIST)

    assert {f.technique for f in result.findings} == {"input_accepted"}
    assert {f.proposed_severity for f in result.findings} == {"low"}
    assert {f.field for f in result.findings} == {"limite", "ordem", "busca"}
    finding = next(f for f in result.findings if f.field == "limite")
    assert finding.case_class == "wrong_type"
    assert finding.declared == "type integer"
    assert finding.baseline_status == 200
    assert finding.observed_status == 200
    assert finding.cwe == 20
    assert finding.status == "needs_triage"


def test_a_server_that_crashes_on_the_forbidden_value_yields_server_error_findings() -> None:
    rig = NegativeRig(Catalog(mode="crash"))

    result = rig.run(LIST)

    assert {f.technique for f in result.findings} == {"input_server_error"}
    assert {f.cwe for f in result.findings} == {755}
    assert all(f.observed_status == 500 for f in result.findings)


@pytest.mark.parametrize(
    ("status", "reason"),
    [(404, "not_found"), (401, "unauthorized"), (403, "unauthorized"), (429, "rate_limited")],
)
def test_answers_that_prove_nothing_are_inconclusive_and_never_findings(
    status: int, reason: str
) -> None:
    rig = NegativeRig(Catalog(forced={("GET", "api/produtos"): status}))

    result = rig.run(LIST)

    assert result.findings == ()
    assert reason in reasons(result)
    assert sum(row.rejected + row.accepted for row in result.by_class) == 0
    assert sum(row.inconclusive for row in result.by_class) >= 1


def test_a_gone_resource_ends_the_remaining_cases_of_that_operation() -> None:
    rig = NegativeRig(Catalog(forced={("GET", "api/produtos"): 404}))

    result = rig.run(LIST)

    assert len(rig.sent("GET")) == 1
    left = [n for n in result.not_tested if n.reason == "not_found" and n.field is None]
    assert left
    assert "não foram enviados" in left[0].message


def test_one_field_changes_per_request_and_the_rest_stays_as_the_probe_proved() -> None:
    rig = NegativeRig(Catalog(mode="validate"))

    rig.run(LIST)

    baseline = {"limite": "10", "ordem": "asc", "busca": "abc"}
    for query in sent_queries(rig):
        assert len(query) == 3
        assert sum(1 for key, value in query.items() if baseline[key] != value) == 1


def test_dry_run_plans_without_sending_or_writing() -> None:
    rig = NegativeRig(Catalog(mode="validate"), allow_writes=True)

    result = rig.run(LIST, CREATE, UPDATE, REMOVE, dry_run=True)

    assert result.dry_run is True
    assert rig.sent() == []
    assert rig.artifacts.negative == {}
    assert result.requests_sent == 0
    assert {case.method for case in result.plan} == {"GET", "POST", "PUT"}
    assert {case.operation_id for case in result.plan} >= {"listarProdutos", "criarProduto"}
    assert all(case.declared for case in result.plan)
    assert all(row.sent == 0 for row in result.by_class)
    assert sum(row.planned for row in result.by_class) == len(result.plan)


def test_the_plan_never_holds_a_delete_even_with_writes_authorized() -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    result = rig.run(LIST, CREATE, UPDATE, ADJUST, REMOVE)

    assert rig.sent("DELETE") == []
    assert rig.catalog.deleted == 0
    assert all(item.operation_id != "removerProduto" for item in result.findings)
    assert "removerProduto" not in {n.operation_id for n in result.not_tested}


def test_a_denied_path_sends_nothing_and_is_reported_as_scope_denied() -> None:
    from tests.fakes.negative_rig import catalog_profile_data

    data = catalog_profile_data()
    data["scope"]["deny_paths"] = ["/api/produtos"]
    rig = NegativeRig(Catalog(), profile_data=data)

    result = rig.run(LIST)

    assert "scope_denied" in reasons(result)
    assert result.findings == ()
    assert result.operations_tested == 0
    assert len(rig.sent()) == 0


def test_the_total_budget_counts_every_request_and_the_cut_is_reported() -> None:
    rig = NegativeRig(Catalog(mode="validate"), max_requests=2)

    result = rig.run(LIST)

    assert result.requests_sent <= 2
    assert len(rig.sent()) <= 2
    assert "budget" in reasons(result)


def test_the_budget_per_operation_cuts_the_extra_cases() -> None:
    rig = NegativeRig(Catalog(mode="validate"), max_cases_per_operation=1)

    result = rig.run(LIST)

    assert len(rig.sent()) == 1
    cut = next(n for n in result.not_tested if n.reason == "budget")
    assert cut.operation_id == "listarProdutos"
    assert "max_cases_per_operation" in cut.message


def test_the_max_requests_flag_only_lowers_the_profile_ceiling() -> None:
    rig = NegativeRig(Catalog(mode="validate"), max_requests=3)
    probe = rig.seed(LIST)

    with pytest.raises(ConfigError, match="max-requests"):
        rig.negative().execute(
            NegativeRequest(product="agenda", run_id=probe.run_id, max_requests=4)
        )
    with pytest.raises(ConfigError, match="max-requests"):
        rig.negative().execute(
            NegativeRequest(product="agenda", run_id=probe.run_id, max_requests=0)
        )
    result = rig.negative().execute(
        NegativeRequest(product="agenda", run_id=probe.run_id, max_requests=1)
    )

    assert result.requests_sent == 1


def test_only_chooses_operations_and_an_unknown_one_is_an_error() -> None:
    rig = NegativeRig(Catalog(mode="validate"), allow_writes=True)
    probe = rig.seed(LIST, CREATE)

    with pytest.raises(ConfigError, match="não existe"):
        rig.negative().execute(
            NegativeRequest(product="agenda", run_id=probe.run_id, only=("inventada",))
        )
    result = rig.negative().execute(
        NegativeRequest(product="agenda", run_id=probe.run_id, only=("criarProduto",))
    )

    assert {r.method for r in rig.sent()} == {"POST"}
    assert result.operations_tested == 1


def test_the_sent_value_never_reaches_any_artifact_log_or_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    with caplog.at_level("DEBUG"):
        result = rig.run(LIST, CREATE, UPDATE, ADJUST)

    assert rig.sent("GET")
    assert rig.sent("POST")
    texts = [
        result.model_dump_json(),
        rig.artifacts.serialized(),
        rig.store.serialized(),
        caplog.text,
        *(finding.evidence for finding in result.findings),
        *(item.message for item in result.not_tested),
    ]
    for marker in SENT_MARKERS:
        assert all(marker not in text for text in texts)
    # O texto longo demais ("a" repetido): o armazém do probe tem hashes de "a", fora da conta.
    assert all("a" * 11 not in text for text in texts if text is not texts[2])


def test_a_registered_secret_never_reaches_the_result() -> None:
    rig = NegativeRig(Catalog(mode="lax"), allow_writes=True)

    result = rig.run(LIST, CREATE, UPDATE)

    text = result.model_dump_json() + rig.artifacts.serialized()
    for secret in ("senha-pa-secreta", "login-pa-xyz", "senha-ad-secreta"):
        assert secret not in text


def test_the_stage_is_tagged_in_the_audit_trail_for_every_request() -> None:
    rig = NegativeRig(Catalog(mode="validate"))

    rig.run(LIST)

    entries = [e for e in rig.store.all_audit() if e.operation_id.startswith("negative:")]
    assert entries
    assert all(e.operation_id == "negative:listarProdutos" for e in entries)


def test_an_unresponsive_target_stops_the_stage_with_the_partial_result() -> None:
    rig = NegativeRig(Catalog(forced={("GET", "api/produtos"): 503}))

    result = rig.run(LIST)

    assert result.status == "stopped_target_unresponsive"
    assert result.stop_message


def test_a_proxy_failure_ends_the_stage_as_stopped_zap() -> None:
    rig = NegativeRig(Catalog())
    probe = rig.seed(LIST)
    original = rig.target._handler

    def broken(request: Any, jar: Any) -> Any:
        if request.operation_id.startswith("negative:"):
            return ExternalToolError("O proxy do ZAP não respondeu.")
        return original(request, jar)

    rig.target._handler = broken

    result = rig.negative().execute(NegativeRequest(product="agenda", run_id=probe.run_id))

    assert result.status == "stopped_zap"
    assert any(n.reason == "stopped" for n in result.not_tested)
    assert rig.artifacts.negative[probe.run_id] == result


def test_an_exhausted_deadline_ends_the_stage_before_any_request() -> None:
    from datetime import timedelta

    rig = NegativeRig(Catalog())
    probe = rig.seed(LIST)

    result = rig.negative().execute(
        NegativeRequest(
            product="agenda",
            run_id=probe.run_id,
            deadline=rig.clock.now() - timedelta(seconds=1),
        )
    )

    assert result.status == "stopped_deadline"
    assert rig.sent() == []


def test_missing_exchanges_are_an_error_for_the_command_and_a_note_inside_the_run() -> None:
    rig = NegativeRig(Catalog())
    probe = rig.run_probe()
    del rig.store.exchanges[probe.run_id]

    with pytest.raises(ConfigError):
        rig.negative().execute(NegativeRequest(product="agenda", run_id=probe.run_id))
    result = rig.negative().execute(
        NegativeRequest(product="agenda", run_id=probe.run_id, tolerate_missing_exchanges=True)
    )

    assert result.status == "completed"
    assert reasons(result) == ["exchanges_unavailable"]
    assert rig.sent() == []


def test_empty_exchanges_are_an_error_for_the_command_and_a_note_inside_the_run() -> None:
    rig = NegativeRig(Catalog())
    probe = rig.seed()

    with pytest.raises(ConfigError, match=r"exchanges\.json vazio"):
        rig.negative().execute(NegativeRequest(product="agenda", run_id=probe.run_id))
    result = rig.negative().execute(
        NegativeRequest(product="agenda", run_id=probe.run_id, tolerate_missing_exchanges=True)
    )

    assert reasons(result) == ["no_exchanges"]


def test_an_unknown_run_is_an_error() -> None:
    rig = NegativeRig(Catalog())

    with pytest.raises(ConfigError):
        rig.negative().execute(NegativeRequest(product="agenda", run_id="20990101T000000Z-abc"))


def test_an_exchange_whose_operation_left_the_openapi_is_reported_not_sent() -> None:
    from tests.fakes.negative_rig import exchange

    rig = NegativeRig(Catalog())
    gone = exchange("sumiu", "GET", "/api/sumiu", "/api/sumiu?limite=1")

    result = rig.run(gone)

    assert reasons(result) == ["operation_not_found"]
    assert rig.sent() == []
