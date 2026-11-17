"""`authz`: BOLA de leitura com identificador na consulta (ADR 0042, parte b)."""

from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.authz_rig import AuthzRig
from tests.fakes.authz_write_rig import (
    PATIENT,
    QUERY_LIST,
    READ_NOTE,
    Notes,
    authz_sent,
    exchange,
    notes_rig,
    run_checks,
)


def run_horizontal(rig: AuthzRig, *exchanges: ExchangeRecord) -> AuthzResult:
    return run_checks(rig, exchanges, "horizontal")


def test_any_account_getting_the_same_body_gives_a_finding_with_the_query_field() -> None:
    rig = notes_rig(Notes(filter_open=True))

    result = run_horizontal(rig, QUERY_LIST)

    (found,) = result.findings
    assert found.technique == "authz_horizontal"
    assert found.fields == ("query:pacienteId",)
    assert (found.actor_account, found.owner_account) == ("pac_b", "pac_a")
    assert found.operation_id == "listarConsultasDoPaciente"
    assert "`pacienteId`" in found.evidence


def test_the_other_account_repeats_the_same_request_and_never_another_value() -> None:
    rig = notes_rig(Notes(filter_open=True))

    run_horizontal(rig, QUERY_LIST)

    urls = {(r.account, r.url.rsplit("/api/", 1)[1]) for r in authz_sent(rig)}
    assert urls == {
        ("pac_a", "consultas?pacienteId=2"),
        ("pac_b", "consultas?pacienteId=2"),
    }


def test_the_severity_is_high_with_an_owned_hint_and_medium_with_the_name_only() -> None:
    hinted = run_horizontal(notes_rig(Notes(filter_open=True)), QUERY_LIST, PATIENT)
    plain = run_horizontal(notes_rig(Notes(filter_open=True)), QUERY_LIST)

    assert [f.proposed_severity for f in hinted.findings if f.fields] == ["high"]
    assert [f.proposed_severity for f in plain.findings] == ["medium"]


def test_a_server_that_denies_the_other_account_gives_no_finding() -> None:
    rig = notes_rig(Notes(filter_open=False))

    result = run_horizontal(rig, QUERY_LIST)

    assert result.findings == ()
    summary = next(c for c in result.checks if c.check == "horizontal")
    assert (summary.tested, summary.candidates) == (1, 1)


def test_a_2xx_with_a_different_body_is_not_a_finding() -> None:
    rig = notes_rig(Notes(filter_open=True, vary_by_account=True))

    result = run_horizontal(rig, QUERY_LIST)

    assert result.findings == ()


def test_a_path_identifier_still_gives_the_finding_with_empty_fields() -> None:
    rig = notes_rig(Notes())  # `GET /api/notas/{id}` devolve a nota a qualquer conta

    result = run_horizontal(rig, READ_NOTE)

    (found,) = result.findings
    assert found.fields == ()
    assert found.proposed_severity == "high"


def test_a_collection_without_an_identifier_is_not_compared() -> None:
    rig = notes_rig(Notes(filter_open=True))
    plain = exchange("listarConsultasDoPaciente", "GET", "/api/consultas", "/api/consultas?page=1")

    result = run_horizontal(rig, plain)

    assert result.findings == ()
    assert [
        n.reason
        for n in result.not_tested
        if n.check == "horizontal" and not n.reason.startswith(("owner_", "public_"))
    ] == ["no_object_identifier"]
    assert authz_sent(rig) == []


def test_an_odd_value_is_ambiguous_and_nothing_is_sent() -> None:
    rig = notes_rig(Notes(filter_open=True))
    odd = exchange(
        "listarConsultasDoPaciente", "GET", "/api/consultas", "/api/consultas?pacienteId=1,2"
    )

    result = run_horizontal(rig, odd)

    assert [
        n.reason
        for n in result.not_tested
        if n.check == "horizontal" and not n.reason.startswith(("owner_", "public_"))
    ] == ["ambiguous_identifier"]
    assert authz_sent(rig) == []


def test_a_declared_id_parameter_adds_the_read_candidate() -> None:
    by_cpf = exchange(
        "buscarPacientePorCpf",
        "GET",
        "/api/pacientes/busca",
        "/api/pacientes/busca?cpf=12345678901",
    )
    without = run_horizontal(notes_rig(Notes()), by_cpf)
    declared = run_horizontal(notes_rig(Notes(), id_parameters=["cpf"]), by_cpf)

    assert without.findings == ()
    assert [
        n.reason
        for n in without.not_tested
        if n.check == "horizontal" and not n.reason.startswith(("owner_", "public_"))
    ] == ["no_object_identifier"]
    (found,) = declared.findings
    assert found.fields == ("query:cpf",)
    assert found.proposed_severity == "medium"


def test_a_denied_path_is_refused_by_the_guard_and_nothing_is_sent() -> None:
    rig = notes_rig(Notes(filter_open=True))
    denied = exchange(
        "listarConsultasDoPaciente", "GET", "/api/consultas", "/api/admin/consultas?pacienteId=2"
    )

    result = run_horizontal(rig, denied)

    assert [r for r in rig.target.requests if "/api/admin/" in r.url] == []
    assert result.findings == ()
    assert [
        n.reason
        for n in result.not_tested
        if n.check == "horizontal" and not n.reason.startswith(("owner_", "public_"))
    ] == ["scope_denied"]


def test_the_query_value_never_reaches_the_artifacts() -> None:
    rig = notes_rig(Notes(filter_open=True))
    secret = exchange(
        "listarConsultasDoPaciente", "GET", "/api/consultas", "/api/consultas?pacienteId=987654321"
    )

    result = run_horizontal(rig, secret)

    assert result.findings
    assert "987654321" not in result.model_dump_json()
