"""`retestar` com o Nuclei (ADR 0122): só os modelos dos achados abertos, e só se houver."""

import pytest

from harness_dast.application.run import RunResult
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.nuclei_findings import NucleiFinding
from harness_dast.domain.nuclei_result import NucleiResult
from tests.fakes.nuclei import nuclei_finding, nuclei_result
from tests.fakes.retest import InMemoryRetestArtifacts
from tests.unit.application.test_retest import (
    AFTER,
    BEFORE,
    _after,
    _fake,
    _finding,
    _request,
    _result,
)
from tests.unit.domain.test_findings_triage_qa import report_with


def _artifacts(**nuclei: object) -> InMemoryRetestArtifacts:
    kept = _finding("a", "op1")
    reports = {BEFORE: report_with(kept, run_id=BEFORE), AFTER: _after([kept], [])}
    return InMemoryRetestArtifacts(reports, nuclei=nuclei)  # type: ignore[arg-type]


def test_reteste_repete_so_os_modelos_dos_achados_do_nuclei_da_execucao_anterior() -> None:
    previous = nuclei_result(
        run_id=BEFORE,
        findings=(
            nuclei_finding("b-id"),
            nuclei_finding("a-id"),
            nuclei_finding("a-id", path="/x"),
        ),
    )
    case, pipeline = _fake(_artifacts(**{BEFORE: previous}))

    case.execute(_request())

    (run,) = pipeline.requests
    assert run.nuclei is True
    assert run.nuclei_templates == (
        "http/misconfiguration/a-id.yaml",
        "http/misconfiguration/b-id.yaml",
    )


def test_sem_nuclei_json_anterior_o_estagio_do_nuclei_fica_desligado() -> None:
    case, pipeline = _fake(_artifacts())

    case.execute(_request())

    (run,) = pipeline.requests
    assert run.nuclei is False
    assert run.nuclei_templates == ()


def test_nuclei_json_anterior_sem_achados_deixa_o_estagio_desligado() -> None:
    case, pipeline = _fake(_artifacts(**{BEFORE: nuclei_result(run_id=BEFORE, findings=())}))

    case.execute(_request())

    (run,) = pipeline.requests
    assert run.nuclei is False
    assert run.nuclei_templates == ()


def test_authz_e_negative_continuam_desligados_no_reteste() -> None:
    previous = nuclei_result(run_id=BEFORE, findings=(nuclei_finding(),))
    case, pipeline = _fake(_artifacts(**{BEFORE: previous}))

    case.execute(_request())

    (run,) = pipeline.requests
    assert (run.authz, run.negative) == (False, False)


# ---- reteste só do Nuclei e classificação dos achados do Nuclei -------------------------------


def _nuclei_run(*, files: bool = True) -> RunResult:
    base = _result(files=False)
    summary = base.summary.model_copy(
        update={"artifacts": {"nuclei.json": "nuclei.json"} if files else {}}
    )
    return RunResult(summary, None)


def _only_nuclei(previous: NucleiResult, current: NucleiResult | None) -> InMemoryRetestArtifacts:
    nuclei = {BEFORE: previous, **({AFTER: current} if current else {})}
    return InMemoryRetestArtifacts({BEFORE: report_with(run_id=BEFORE)}, nuclei=nuclei)


def _previous(*findings: NucleiFinding) -> NucleiResult:
    return nuclei_result(run_id=BEFORE, findings=findings)


def test_sem_achado_do_zap_o_reteste_roda_so_o_nuclei_com_os_modelos_dos_achados_abertos() -> None:
    opened = nuclei_finding("a-id", severity="high")
    artifacts = _only_nuclei(_previous(opened), nuclei_result(run_id=AFTER, findings=(opened,)))
    case, pipeline = _fake(artifacts, _nuclei_run())

    outcome = case.execute(_request(fail_on="high"))

    (run,) = pipeline.requests
    assert run.nuclei_only is True
    assert run.nuclei is True
    assert run.only == ()
    assert run.nuclei_templates == ("http/misconfiguration/a-id.yaml",)
    assert outcome.report is not None
    (entry,) = outcome.report.entries
    assert (entry.origin, entry.result, entry.finding_id) == (
        "nuclei",
        "reproduced",
        "U-" + opened.fingerprint[:8],
    )
    assert entry.operation_id == "nuclei:a-id"
    assert "reprodução, não confirmação independente" in entry.reason
    assert outcome.report.only == ()
    assert outcome.exit_code == 1
    assert AFTER in artifacts.written


def test_o_modelo_que_nao_voltou_e_not_reproduced_so_com_o_estagio_concluido() -> None:
    opened = nuclei_finding("a-id")
    gone = nuclei_result(run_id=AFTER, findings=())
    artifacts = _only_nuclei(_previous(opened), gone)
    case, _ = _fake(artifacts, _nuclei_run())

    outcome = case.execute(_request(fail_on="none"))

    assert outcome.report is not None
    assert [item.result for item in outcome.report.entries] == ["not_reproduced"]
    assert "não prova que o problema foi corrigido" in outcome.report.entries[0].reason
    assert outcome.exit_code == 0


def test_o_estagio_parado_deixa_o_achado_como_not_tested() -> None:
    opened = nuclei_finding("a-id")
    stopped = nuclei_result("stopped_window", run_id=AFTER, findings=(), message="janela")
    case, _ = _fake(_only_nuclei(_previous(opened), stopped), _nuclei_run())

    outcome = case.execute(_request())

    assert outcome.report is not None
    assert [item.result for item in outcome.report.entries] == ["not_tested"]


def test_se_o_run_parou_antes_do_nuclei_json_nao_ha_retest() -> None:
    opened = nuclei_finding("a-id")
    case, _ = _fake(_only_nuclei(_previous(opened), None), _nuclei_run(files=False))

    outcome = case.execute(_request())

    assert outcome.report is None


def test_sem_achado_do_zap_nem_do_nuclei_continua_recusando() -> None:
    artifacts = InMemoryRetestArtifacts({BEFORE: report_with(run_id=BEFORE)})
    case, pipeline = _fake(artifacts)

    with pytest.raises(ConfigError, match="severidade alta ou média"):
        case.execute(_request())

    assert pipeline.requests == []


def test_finding_aceita_a_impressao_digital_de_um_achado_do_nuclei() -> None:
    kept = _finding("a", "op1")
    first, second = nuclei_finding("a-id"), nuclei_finding("b-id")
    artifacts = InMemoryRetestArtifacts(
        {BEFORE: report_with(kept, run_id=BEFORE)},
        nuclei={
            BEFORE: _previous(first, second),
            AFTER: nuclei_result(run_id=AFTER, findings=(second,)),
        },
    )
    case, pipeline = _fake(artifacts, _nuclei_run())

    outcome = case.execute(_request(findings=(second.fingerprint,)))

    (run,) = pipeline.requests
    assert run.nuclei_only is True
    assert run.nuclei_templates == ("http/misconfiguration/b-id.yaml",)
    assert outcome.report is not None
    assert [item.fingerprint for item in outcome.report.entries] == [second.fingerprint]


def test_finding_so_do_zap_nao_liga_o_nuclei_mesmo_com_achados_abertos() -> None:
    kept = _finding("a", "op1")
    artifacts = InMemoryRetestArtifacts(
        {BEFORE: report_with(kept, run_id=BEFORE), AFTER: _after([kept], [])},
        nuclei={BEFORE: _previous(nuclei_finding("a-id"))},
    )
    case, pipeline = _fake(artifacts)

    case.execute(_request(findings=(kept.fingerprint,)))

    (run,) = pipeline.requests
    assert run.nuclei is False
    assert run.nuclei_only is False
    assert run.only == ("op1",)


def test_com_achados_do_zap_e_do_nuclei_o_retest_traz_as_duas_origens() -> None:
    kept = _finding("a", "op1")
    opened = nuclei_finding("a-id")
    artifacts = InMemoryRetestArtifacts(
        {BEFORE: report_with(kept, run_id=BEFORE), AFTER: _after([kept], [])},
        nuclei={BEFORE: _previous(opened), AFTER: nuclei_result(run_id=AFTER, findings=(opened,))},
    )
    case, pipeline = _fake(artifacts)

    outcome = case.execute(_request(fail_on="none"))

    (run,) = pipeline.requests
    assert (run.nuclei_only, run.nuclei, run.only) == (False, True, ("op1",))
    assert outcome.report is not None
    assert [(item.origin, item.result) for item in outcome.report.entries] == [
        ("zap", "reproduced"),
        ("nuclei", "reproduced"),
    ]
    assert outcome.report.counts.reproduced == 2


def test_excesso_de_finding_sobre_o_teto_conta_os_achados_do_nuclei() -> None:
    first, second = nuclei_finding("a-id"), nuclei_finding("b-id")
    artifacts = _only_nuclei(_previous(first, second), None)
    case, pipeline = _fake(artifacts)

    with pytest.raises(ConfigError, match="acima do teto"):
        case.execute(_request(findings=(first.fingerprint, second.fingerprint), max_findings=1))

    assert pipeline.requests == []
